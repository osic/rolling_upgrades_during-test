import argparse
from ConfigParser import SafeConfigParser
import json
from multiprocessing import Pipe, Process
import os
import sys
import logging

from test_project import test_nova
from test_project import test_swift
from test_project import test_keystone

LOG = logging.getLogger(__name__)

class ArgumentParser(argparse.ArgumentParser):
    def __init__(self):
        desc = "Tests the uptime for a given length of time against a list of services."
        usage_string = "[-s/--services] ([-t/--time] | [-d/--daemon]) [-o/--output-file]"

        super (ArgumentParser, self).__init__(
            usage=usage_string, description=desc)

        self.add_argument(
            "-s", "--services", metavar="<comma-delimited services list>",
            required=False, default=None)

        group = self.add_mutually_exclusive_group()
        group.add_argument(
            "-t", "--times", metavar="<amount of seconds to run>",
            required=False, default=60, type=int)
        group.add_argument(
            "-d", "--daemon", required=False, action='store_true')

        self.add_argument(
            "-o", "--output-file", metavar="<path to output file>",
            required=False, default=None)
	
        self.add_argument(
            "-m", "--multiprocess", required=False, action='store_true')


def entry_point():
    cl_args = ArgumentParser().parse_args()
    
    # Check if a process is already running for script
    if cl_args.multiprocess:
        pass
    else:
        checkRunningPid()

    # Initialize Config Variables
    config = SafeConfigParser()
    if os.path.isfile("../tempest/etc/tempest.conf"):
        config.read("../tempest/etc/tempest.conf") #initialize environment from tempest.conf
        user = config.get("auth", "admin_username")
        password = config.get("auth", "admin_password")
        tenant = config.get("auth", "admin_project_name")
        image_id = config.get("compute", "image_ref")
        auth_url = config.get("identity", "uri")
        keystone_auth_url = config.get("identity", "uri_v3")
        flavor_size = config.get("compute", "flavor_ref")
    else:
        config.read("os.cnf") #add custom config
        user=config.get("openstack", "user")
        password=config.get("openstack", "password")
        tenant=config.get("openstack", "tenant")
        auth_url=config.get("openstack", "auth_url")
        keystone_auth_url=config.get("openstack", "keystone_auth_url")
        image_id=config.get("openstack", "image_id")
        flavor_size=config.get("openstack", "flavor_size")

    config.read("os.cnf") #add custom config
    version = config.get("openstack", "version")
    services_list = config.get("openstack", "services_list")
    instance_name = config.get("openstack", "instance_name")
    container_name = config.get("openstack", "container_name")
    object_name = config.get("openstack", "object_name")
    daemon_file = config.get("openstack", "daemon_file") or os.path.join(sys.prefix, "during.uptime.stop")
    output_file = cl_args.output_file or config.get("openstack", "output_file")
	
    print "To stop script please create during.uptime.stop file in: " + sys.prefix
    
    if cl_args.daemon and os.path.exists(daemon_file):
        os.remove(daemon_file)

    services = [service.strip() for service in (cl_args.services or services_list).split(",")]
    time_value = cl_args.daemon if cl_args.daemon else cl_args.times

    pipes = []
    service = None
    for s in services:
	if s == "nova":
	    mad = test_nova.ApiUptime(version, user, password, tenant, auth_url)
            p, c = Pipe()
            pipes.append(p)
            Process(target=mad.test_create_delete_server, args=(c,s,time_value,flavor_size,instance_name,image_id,)).start()
            c.close()
	    service = s
	if s == "swift":
	    mad = test_swift.ApiUptime(version, user, password, tenant, auth_url)
            p, c = Pipe()
            pipes.append(p)
            Process(target=mad.test_create_delete_container, args=(c,s,time_value,container_name,object_name,)).start()
	    c.close()
	    service = s
	if s == "keystone":
	    mad = test_keystone.ApiUptime(version, user, password, tenant, keystone_auth_url)
            p, c = Pipe()
            pipes.append(p)
            Process(target=mad.test_create_validate_token, args=(c,s,time_value,)).start()
            c.close()
	    service = s

    if cl_args.daemon:
        while True:
            if os.path.exists(daemon_file):
                for pipe in pipes:
                    pipe.send("STOP")
                break

    outputs = [pipe.recv() for pipe in pipes]
    final_output = {k: v for d in outputs for k, v in d.items()}
    
    #Will tweak later
    #if len(services) == 1:
    #    output_file = service + '_' + output_file

    if output_file is None or output_file == '':
        print json.dumps(final_output)
    else:
        with open(output_file, 'w') as out:
	    print json.dumps(final_output)
            out.write(json.dumps(final_output))
	    print "Output here: " + output_file


def checkRunningPid():
    pid = str(os.getpid())
    pid_file = '%s/during_test_tmp.pid' % os.environ['HOME']

    if os.path.isfile(pid_file):
	print "Reading from %s checking if process is still running." % pid_file
        r_pid = int(open(pid_file,'r+').readlines()[0])
        ps_command = "ps -o command= %s | grep -Eq 'python call_test'" % r_pid
        process_exit = os.system(ps_command)
        if process_exit == 0:
	    sys.exit("Looks like process is already running please kill pid: kill " + r_pid)
        else:
	    print "Process is not running. Recording pid %s in %s. DO NOT DELETE THIS FILE" % (pid,pid_file)
	    f = open(pid_file, 'w')
	    f.write(pid)
	    f.close()
    else:
	print "Recording pid %s in %s. DO NOT DELETE THIS FILE" % (pid,pid_file)
	f = open(pid_file, 'w')
	f.write(pid)
	f.close()


if __name__ == "__main__":
    entry_point()
