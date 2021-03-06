import json
import os
import requests
import sys
import time
import unittest
import urllib2

from datetime import datetime
from inspect import currentframe, getframeinfo
from multiprocessing import Pipe, Process
from time import sleep

class ApiUptime(unittest.TestCase):
    def __init__(self, version, username, password, tenant, auth_url):
	self.server_id = ''
	self.url = auth_url + '/'
        self.data = '{"auth":{"passwordCredentials":{"username":"' + username + '","password": "' + password + '"},"tenantName": "' + tenant + '"}}'
	self.error_output = ''
	self.frameinfo = getframeinfo(currentframe())

    def get_token(self):
        get_token = None
        headers = {'Content-Type': 'application/json'}
        url = self.url + 'tokens'
        req = urllib2.Request(url, self.data, {'Content-Type': 'application/json'})

	try:
            f = urllib2.urlopen(req)
	except Exception as e:
	    if any(c in str(e) for c in ('503','404')):
		self.error_output = str(e) + "  line " + str(self.frameinfo.lineno)
		return False
	    else:
		self.error_output = str(e) + "  line " + str(self.frameinfo.lineno)
		return False		

        for x in f:
            d = json.loads(x)
            token = d['access']['token']['id']
	f.close()
        header = {'X-Auth-Token': token}
        return header

    def get_nova_url(self):
	nova_url = None
        headers = {'Content-Type': 'application/json'}
        url = self.url + 'tokens'
        req = urllib2.Request(url, self.data, {'Content-Type': 'application/json'})

        try:
            f = urllib2.urlopen(req)
        except Exception as e:
	    if any(c in str(e) for c in ('503','404')):
		self.error_output = str(e) + "  line " + str(self.frameinfo.lineno)
                return False
	    else:
		self.error_output = str(e) + "  line " + str(self.frameinfo.lineno)
		return False

	try:
            for x in f:
                d = json.loads(x)
                for j in d['access']['serviceCatalog']:
                    if j['name'] == 'nova':
                        for k in j['endpoints']:
                            nova_url = k['internalURL']
	except Exception as e:
	    print e
	    f.close()
	    return False
        f.close()

	if nova_url == None: return False

        return nova_url + '/'

    def _wait_until(self, url, headers):
	get = None
	start_time = time.time()
	build_time = 0
	avg_build_time = 0

	while get  <> 'ACTIVE':
            #Sending requests to OS
            try:
                response = requests.get(url, headers=headers)
            except Exception as e:
                print "Received " + str(e) + " retreiving server status in _wait_until."
                self.error_output += "Received " + str(e) + " retreiving url in _wait_until."
                return 'ERROR', 0

	    #Analyzing response
            if '200' in str(response):
                get = response.json()['server']['status']
                build_time = int(time.time() - start_time)
                if build_time > 29 or get == 'ERROR':
		    if get != None:
		        self.error_output += "Timed out or got error for status: " + str(get)
		    else:
			self.error_output += "Timed out or got error (or null) for status in wait"
                    return str(get), 0
	    else:
		if response:
		    self.error_output += "Error retrieving status in wait: " + str(response)
		else:
		    self.error_output += "Error retrieving status in wait. Response was 'None'"
		get = 'ERROR'
		return get, 0

	#Get average build time
	avg_build_time = build_time

	#Creating VM every 30 seconds so wait
	while build_time <= 29:
	    build_time = int(time.time() - start_time)

	return get, avg_build_time

    def write_status(self, service, status, build_start, error, total_down, duration, test_start ):
            status = {"service": service, service + "_status": status, "timestamp": build_start, "error": error, service + "_total_down": total_down, service + "_duration": duration, "time_run_started": test_start}
            f = open('../output/nova_status.json','a')
            f.write(json.dumps(status) + "\n")
            f.close()


    def _delete_server_list(self, nova_url, headers, name=None):
	server_delete = ''

	try:
            response = requests.get(nova_url + 'servers', headers=headers)
	except Exception as e:
	    print "Received: " + str(e) + " trying to get list to delete servers"
	    self.error_output += "Received: " + str(e) + " trying to get list to delete servers"
	    return False

        if '401' in str(response):
            print "Getting token, it may have expired."
	    self.error_output += "Received: " + str(response) + " trying to get list to delete servers"
            self.headers = self.get_token()
            return False

	if any(c in str(response) for c in ('201','200','202')):

	    response = response.json()

	    for i in response['servers']:
		server_delete = ''
	        if i['name'] == name:
		    while '204' not in str(server_delete):
	                server_delete = self.delete_server(nova_url, headers, i['id'])
			if '204' not in str(server_delete):
				print "Error trying to delete server : " + i['id'] + " " + server_delete
				self.error_output += "Error trying to delete server: " + i['id'] + " " + server_delete
				sleep(5)
			if '404' in str(server_delete): break
            return True


    def create_server(self,url,headers,name, image, flavor, data):
	avg_build_time = 0
	url = url + '/servers'
	try:
	    response = requests.post(url, data=data,headers=headers)
	except Exception as e:
	    self.error_output = str(e) + " creating server on line " + str(self.frameinfo.lineno)
            return 'ERROR', 0

	if any(c in str(response) for c in ('201','202')):
            pass
        else:
            if str(response) == None:
		response = "Null value received"
            self.error_output = str(response) + " creating server on line " + str(self.frameinfo.lineno)
            return str(response), avg_build_time

	#Wait until active
	response = response.json()
	self.server_id = response['server']['id']
        status, avg_build_time = self._wait_until(url + '/' + self.server_id, headers)
	return status, avg_build_time

    def delete_server(self, url, headers, server_id=None):
    	if server_id == None: return 'No server id to delete server'

	if server_id:
	    pass
	else:
	    server_id = self.server_id

        url = url + '/servers/' + str(server_id)
        try:
	    response = str(requests.delete(url, headers=headers))
	except Exception as e:
	    self.error_output = str(e) + " deleting server  on line " + str(self.frameinfo.lineno)
	    return 'ERROR'
	
	if '204' not in response:
	    self.error_output = "Error deleting server: " + str(server_id) + "  on line " + str(self.frameinfo.lineno)
	return response

    def report(self, conn, service, success, total, start_time, end_time, down_time, duration, avg_build_time):
        success_pct = 100 * (float(success)/total)

	uptime_pct = 100 - round((float(down_time)/duration * 100), 2)

	print "*** Nova uptime pct: " + str(uptime_pct) + "% ***"

        conn.send({
            service: {
		"project": service,
                "success_pct": success_pct,
                "total_requests": total,
                "successful_requests": success,
                "failed_requests": total - success,
                "start_time": start_time,
                "end_time": end_time,
		"down_time": down_time,
		"avg_build_time": avg_build_time,
		"uptime_pct": uptime_pct}})
        conn.close()

    def test_create_delete_server(self, conn, service, times, flavor=None, name=None, image=None):
        output = []
        start_time = 0
        status = None
        down_time = None
        server = ''
	total_down_time = 0
	avg_build_time = 0
	server_delete = ''
	test_finish_time = None
	duration = 0

	server_data = '{"server":{"name": "' + name + '", "imageRef": "' + image + '", "flavorRef": "' + flavor + '"}}'

	if times is True:
            times = xrange(sys.maxint)
        else:
            times = xrange(times)

        open('../output/nova_status.json','w')

	headers  = self.get_token()
        nova_url = self.get_nova_url()

	build_start = str(datetime.now().strftime("%Y-%m-%dT%H:%M:%S%z"))

        for _ in times:

            if conn.poll() and conn.recv() == "STOP":
		print "Ending Nova during testing."
                break
	    elif os.path.isfile('/usr/during.uptime.stop'):
		print "Ending Nova during testing."
                break

	    start_time = time.time()

	    try:
                if headers == False:
                    print "Trouble getting token"
		    self.assertNotEqual(headers,False)
                if nova_url == False:
                    print "Please check if you have Nova installed."
                    self.assertNotEqual(nova_url,False)

                #Create server
                server, build_time = self.create_server(nova_url,headers,name,image,flavor,server_data)
                print "server create: " + str(server)

		#If status is active send true else send false
                self.assertTrue(server == 'ACTIVE')

		avg_build_time += build_time

		#Delete server
                server_delete = self.delete_server(nova_url, headers, self.server_id)
	        print "server delete: " + str(server_delete)
		self.assertIn('204',server_delete)

                #Write to status log
		status_timestamp = str(datetime.now().strftime("%Y-%m-%dT%H:%M:%S%z"))
                #self.write_status(service, 1, str(datetime.now().strftime("%Y-%m-%dT%H:%M:%S%z")))
                output.append(True)

		#Done for aggregating total test duration
		done_time = time.time()
		error = None
		status = 1
            except Exception as e:
	   	#print "Failed Nova: " + str(e)
		status = 0

		if self.error_output != None:
		    print self.error_output + ", " + str(e)
		    self.error_output = self.error_output + ", " + str(e) + " line " + str(self.frameinfo.lineno)
		else:
		    self.error_output = str(e) + " line " + str(self.frameinfo.lineno)

		if server == None:
		    pass
		elif '401' in str(server) or '401' in str(server_delete):
		    headers = False
	        else:
		    delete_list_status = False
		    #Remove all servers
		    while delete_list_status != True:
		        delete_list_status = self._delete_server_list(nova_url, headers, name)
                        if os.path.isfile('/usr/during.uptime.stop'):
		            print "Ending Nova during testing."
                            break
		        sleep(1)
		        

                #Record down time
                status_timestamp = str(datetime.now().strftime("%Y-%m-%dT%H:%M:%S%z"))

                #Write to status log
                #self.write_status(service, 0, status_timestamp, "Failed Nova: " + str(e))
		output.append(False)

		if headers == False:
		    print "Attempting to retrieve token and url"
		    headers = self.get_token()
		    nova_url = self.get_nova_url()

                done_time = time.time()
                total_down_time += (done_time - start_time)

	    #Aggregating total run time of test
	    duration += (done_time-start_time)
	    self.write_status(service,status,status_timestamp,self.error_output,total_down_time,duration,str(build_start))
            self.error_output = ''
	    self.server_id = ''

	self._delete_server_list(nova_url, headers, name)
	avg_build_time = avg_build_time/1

        self.report(conn, service, sum(output),
                    len(output), str(build_start), str(datetime.now().strftime("%Y-%m-%dT%H:%M:%S%z")), total_down_time, duration, avg_build_time)
