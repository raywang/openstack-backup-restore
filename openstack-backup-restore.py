#!/usr/bin/python3
# -*- coding: utf-8 -*-
# Ray Wang, Dec, 2014
# 
# What to Back Up:
#   * Database
#       * Physical (Raw) Versus Logical Backups
#         Physical backups consist of raw copies of the directories and files
#         that store database contents. This type of backup is suitable for 
#         large, important databases that need to be recovered quickly when 
#         problems occur.
#
#         Logical backups save information represented as logical database 
#         structure (CREATE DATABASE, CREATE TABLE statements) and content 
#         (INSERT statements or delimited-text files). This type of backup 
#         is suitable for smaller amounts of data where you might edit the 
#         data values or table structure, or recreate the data on a different 
#         machine architecture.
#
#   * File System 
#       Backup include /etc/<service_name> and /var/lib/<service_name>
#       http://docs.openstack.org/openstack-ops/content/backup_and_recovery.html
#       * compute <e.g. nova>
#       * image catalog and delivery <e.g. glance>
#       * identify <e.g. keystone>
#       * block storage <e.g. cinder>
# 
# Revovering Backup
#   Retore will be from the latest backup directory of the service
#       * stop services
#       * restore the relavent db
#       * copy the backed up dir to /etc
#       * start services
#
# usage:
#   ./openstack-backup-restore.py backup --mysql -u root -pubuntu --to_dir test --keystone --nova --glance --cinder --neutron
#
#   ./openstack-backup-restore.py restore --mysql -u root -pubuntu --from_dir test --keystone --nova --glance --cinder --neutron

import pdb

import os
import sys
import argparse
import subprocess
import shutil
from datetime import datetime


def parse_args():
    parser = argparse.ArgumentParser(description='Backup/Restore OpenStack \
            environment.')

    parser.add_argument("action", metavar="backup | restore", 
                        choices=['backup', 'restore'], 
                        help="Backup OpenStack environment.")

    parser.add_argument("-u", "--db_user", help="Database User", default="root")
    parser.add_argument("-p", "--db_password", help="Database Password", 
                        default="")

    parser.add_argument("--db_host", help="Database Host", default="127.0.0.1")
    parser.add_argument("--to_dir", help="Backup Directory", default=".")
    parser.add_argument("--from_dir", help="Restore Directory", default=".")
    parser.add_argument("--mysql", help="Backup MySQL", action="store_true")
    parser.add_argument("--nova", help="Backup Nova", action="store_true")
    parser.add_argument("--glance", help="Backup Glance", action="store_true")
    parser.add_argument("--cinder", help="Backup Cinder", action="store_true")
    parser.add_argument("--neutron", help="Backup Neutron", action="store_true")
    parser.add_argument("--keystone", help="Backup Keystone", action="store_true")
    
    return parser.parse_args()


def get_databases(args):

    """get databases that need to be backed up"""

    list_db = "mysql --user={} --password={} --host={}  \
                --skip-column-names --silent -e".format(
                args.db_user, 
                args.db_password, 
                args.db_host)

    cmd = list_db.split()
    cmd.append('show databases')
    
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE) 
    stdout, stderr = p.communicate()
    db_list = stdout.decode("utf-8").split()

    # no backup databases
    no_backup = ['information_schema', 'performance_schema', 'test']

    for i in no_backup:
        try:
            db_list.remove(i)
        except ValueError:
            continue
   
    return db_list

    
def backup_db(args):

    """ Backup MySQL Database"""

    timestamp = datetime.now().strftime('%Y%m%d%H%M')
    mysql_backup_dir = "{}/{}-{}".format(args.to_dir, "mysql", timestamp)

    if not os.path.exists(mysql_backup_dir):
        if not os.path.exists(args.to_dir):
            os.mkdir(args.to_dir)
        os.mkdir(mysql_backup_dir)

    if not os.path.isdir(args.to_dir):
        print("ERROR: {} is not a directory.".format(args.to_dir))
        return

    db_list = get_databases(args)

    for db in db_list:

        filename = "{}/{}.sql".format(mysql_backup_dir, db)

        with open(filename, "w") as f:

            if db == "mysql":
                cmd = "mysqldump --user={} --password={} --host={} --events {}".format(
                        args.db_user, 
                        args.db_password, 
                        args.db_host, 
                        db)
            else:
                cmd = "mysqldump --user={} --password={} --host={} {}".format(
                        args.db_user, 
                        args.db_password, 
                        args.db_host, 
                        db)

            cmd = cmd.split()

            p = subprocess.Popen(cmd, stdout=f)
            ret = p.wait()
            if ret > 0:
                print("ERROR: backup {} fail!".format(db))

def restore_db(args, db=None):
    """Restore databases from .sql files"""

    if not os.path.exists(args.from_dir):
        print("ERROR: {} is not exist.".format(args.from_dir))
        return

    if not os.path.isdir(args.from_dir):
        print("ERROR: {} is not a valid directory.".format(args.from_dir))
        return

    mysql_dir = "{}/{}".format(args.from_dir, [f for f in 
                os.listdir(args.from_dir) if f.startswith("mysql-")][-1])

    if db is not None:
        db_files = ['{}.sql'.format(db)]
    else:
        db_files = [f for f in os.listdir(mysql_dir) if f.endswith('.sql')]

    for f in db_files:
        cmd = "mysql --user={} --password={} --host={} {}".format(
                args.db_user, args.db_password, args.db_host, f[:-4])
        cmd = cmd.split()

        path_to_file = "{}/{}".format(mysql_dir, f)
        input_cmd = "{} {}".format("source", path_to_file).encode('utf-8')
                           
        p = subprocess.Popen(cmd, stdin=subprocess.PIPE, 
                            stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE)

        stdout, stderr = p.communicate(input=input_cmd)

        ret = p.wait()
        if ret > 0:
            print("ERROR: restore {} fail!".format(f))
        
def backup_openstack(args, service):

    """Backup OpenStack Services"""

    if not os.path.exists(args.to_dir):
        os.mkdir(args.to_dir)

    service_etc = "/etc/{}".format(service)
    service_var = "/var/lib/{}".format(service)
    service_files = [service_etc, service_var]

    timestamp = datetime.now().strftime('%Y%m%d%H%M')
    service_backup_dir = "{}/{}-{}/".format(args.to_dir, service, timestamp)

    for dir in service_files:
        if not os.path.exists(dir):
            print("The {} is not exist.".format(dir))

        shutil.copytree(dir, "{}/{}".format(service_backup_dir, 
                        os.path.dirname(dir).replace('/', '')))


def restore_openstack(args, service):
    """Only support restore openstack from the latest timestamped directory"""
    
    if service is 'keystone':
        services = ['keystone-api']

    if service is 'nova':
        services = ['nova-api', 'nova-cert', 'nova-scheduler', \
                    'nova-objectstore', 'nova-consoleauth', 'nova-novncproxy']

    if service is 'glance':
        services = ['glance--api']

    if service is 'cinder':
        services = ['cinder--api']

    if service is 'neutron':
        services = ['neutron-server']

    #pdb.set_trace()
    start_stop_service('stop', services, True)
    restore_db(args, service)

    # backup the orignal first
    shutil.move('/etc/{}'.format(service), '/etc/{}.orig'.format(service))
    shutil.move('/var/lib/{}'.format(service), '/var/lib/{}.orig'.format(service))

    # copy the backed up dir to /etc
    if not os.path.exists(args.from_dir):
        print('ERROR: {} is not exist.'.format(args.from_dir))
        return

    if not os.path.isdir(args.from_dir):
        print('ERROR: {} is not a valid directory.'.format(args.from_dir))
        return

    service_backups = [f for f in os.listdir(args.from_dir) if f.startswith('{}-'.format(service))]
    service_backups.sort()
    service_dir = '{}/{}'.format(args.from_dir, service_backups[-1])

    shutil.copytree('{}/etc'.format(service_dir), '/etc/{}'.format(service))
    shutil.copytree('{}/varlib'.format(service_dir), '/var/lib/{}'.format(service))

    start_stop_service('start', services, True)
    

def start_stop_service(action, services, ignore_error=False):
    """start or stop service before restore"""

    if type(services) is not list:
        services = services.split()

    for service in services:
        cmd = 'sudo {} {}'.format(action, service)
        cmd = cmd.split()
        print("{} {}...".format(action, service))
        p = subprocess.Popen(cmd, stdin=subprocess.PIPE, 
                            stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE)

        if ignore_error is True:
            return

        ret = p.wait()
        if ret > 0:
            print("ERROR: {} service {} fail!".format(action, service))


def main():

    args = parse_args()

    if args.action == 'backup':

        if args.mysql:
            print("mysql will be backed up")
            backup_db(args)

        if args.keystone:
            print("Keysotne will be backed up")
            backup_openstack(args, "keystone")

        if args.nova:
            print("nova will be backed up")
            backup_openstack(args, "nova")

        if args.glance:
            print("glance will be backed up")
            backup_openstack(args, "glance")

        if args.cinder:
            print("cinder will be backed up")
            backup_openstack(args, "cinder")

        if args.neutron:
            print("neutron will be backed up")
            backup_openstack(args, "neutron")

    elif args.action == 'restore':

        if args.mysql:
            print("mysql will be restored")
            restore_db(args)

        if args.keystone:
            print("Keysotne will be restored")
            restore_openstack(args, "keystone")

        if args.nova:
            print("nova will be restored")
            restore_openstack(args, "nova")

        if args.glance:
            print("glance will be restored")
            restore_openstack(args, "glance")

        if args.cinder:
            print("cinder will be restored")
            restore_openstack(args, "cinder")

        if args.neutron:
            print("neutron will be restored")
            restore_openstack(args, "neutron")

if __name__ == '__main__':
    sys.exit(main())
