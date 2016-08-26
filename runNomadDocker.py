#!/usr/bin/env python
"""
nomad docker doesn't allow us to do volumes, which hurts.
This is a work-around.  I hope they get their act together soon.

all META keys are capitalized by NOMAD, so be sure to define your _LABELS as uppercase.

required keys:
IMAGE -- name of the docker image to pull.

optional:
NOMAD_META_REGISTRY_URL = the URL for the regitry to pull from.

nomad do HOST export networking at all, so you have to specify it special in the env {} config.
NOMAD_META_NETWORK_LABELS = "" space seperated list of network labels.
NOMAD_PORT_<label> = '' IP port to expose inside the container.
NOMAD_IP_<label> = '' IP ADDRESS to expose.

NOMAD_HOST_PORT_<label> = '' IP port to expose on the host.

nomad doesn't do volumes at all. currently only bind mounts are supported. here is how to do them:
NOMAD_META_VOLUME_LABELS="" is a space seperated list of volume labels (just like network labels)
NOMAD_META_SRC_<LABEL>=""  the source of the volume.
NOMAD_META_DST_<LABEL>="" the destination of the volume.
NOMAD_META_MODE_<LABEL>="" the mode (rw/ro) of the volume.  if missing defaults to rw.
"""
from __future__ import print_function
import os
import signal
import sys

from docker import Client

#used for signal, yes globals suck, get over it.
RUNNINGID=0
DEBUG=True

def main(buildNumber):
    """main code"""
    global RUNNINGID
    cli = Client(base_url='unix://var/run/docker.sock')
    # specify the network mode, port bindings, and volume mounts.
    # this is how the docker python client wants these parameters
    if os.environ.has_key('NOMAD_META_NETWORK_LABELS'):
	networkLabels = os.environ['NOMAD_META_NETWORK_LABELS']
    else:
	networkLabels = ""
    portBindings = {}
    for label in networkLabels.split():
	port = os.environ['NOMAD_PORT_{}'.format(label)]
	ip = os.environ['NOMAD_IP_{}'.format(label)]
	if os.environ.has_key('NOMAD_HOST_PORT_{}'.format(label)):
	    hostPort = os.environ['NOMAD_HOST_PORT_{}'.format(label)]
	else:
	    hostPort = None
	portBindings[port] = (ip, hostPort)
	print("exposing container port {} to external ip:port {}:{}".format(port, ip, hostPort))
    if os.environ.has_key('NOMAD_META_VOLUME_LABELS'):
	volumeLabels = os.environ['NOMAD_META_VOLUME_LABELS']
    else:
	volumeLabels = ""
    volumes = {}
    for label in volumeLabels.split():
	src = os.environ['NOMAD_META_SRC_{}'.format(label)]
	dst = os.environ['NOMAD_META_DST_{}'.format(label)]
	if os.environ.has_key('NOMAD_META_MODE_{}'.format(label)):
	    mode = os.environ['NOMAD_META_MODE_{}'.format(label)]
	else:
	    mode = 'rw'
	volumes[src] = {'bind':dst, 'mode':mode}
	print("binding volume {} src:dst:mode {}:{}:{}".format(label,src,dst,mode))
    labels = {}
    # just move all the nomad stuff into docker labels... why not!
    for k in os.environ.keys():
	#redefine them all without the NOMAD_META prefix.
	if 'NOMAD' in k:
	    newk = k.replace('NOMAD_META_','')
	    labels[newk] = os.environ[k]
    hostConfig  = cli.create_host_config(port_bindings=portBindings,
		    binds=volumes)
    serviceName = os.environ['NOMAD_META_IMAGE']
    dockerName = "{}-{}".format(serviceName, os.environ['NOMAD_ALLOC_ID'])
    if os.environ.has_key('NOMAD_META_REGISTRY_URL'):
	registryURL = os.environ['NOMAD_META_REGISTRY_URL']
    else:
	registryURL = ""
    imageTag = buildNumber
    registry = '%s%s' % (registryURL, serviceName)
    image = "{}:{}".format(registry, imageTag)
    print("will download image {}:{}".format(registry, imageTag))
    cli.pull(repository=registry, tag=imageTag, stream=False)
    containers = cli.containers(all=True,filters={'name':image})
    for i in containers:
	if i['Image'] == image:
	    # currently running, we should stop it.
	    if i['State'] == 'running':
		print("stoppping container {} with ID {}".format(i['Image'], i['Id']))
		#cli.stop(i['Id'])
		#cli.remove_container(i['Id'])
	    else:
		print('container {} exists, but is not running, removing id {}'.format(i['Image'], i['Id']))
		#cli.remove_container(i['Id'])
    container = cli.create_container(image=image, detach=True, name=dockerName,
                                     ports=[port], environment=labels,
				     labels=labels, host_config=hostConfig)
    print("created container: {}".format(container))
    id=container.get('Id')
    RUNNINGID=id
    cli.start(container=id)
    print('container started..: retrieve and print stdout/err...')
    for msg in cli.logs(container=id, stream=True, stdout=True, stderr=True):
        print(msg, end="")

def cleanupDocker(signal, frame):
    """stop container"""
    cli = Client(base_url='unix://var/run/docker.sock')
    if RUNNINGID:
	print("stopping container: {}".format(RUNNINGID))
	cli.stop(RUNNINGID)
    sys.exit(0)

signal.signal(signal.SIGINT, cleanupDocker)

def printDic(d):
    """for printing os.environ, pprint doesn't do it well
    """
    for k in d.keys():
	print("{}: {}".format(k, d[k]))

if __name__ == '__main__':
    try:
	buildNumber = sys.argv[1]
    except IndexError:
	buildNumber = 'latest'
    try:
	print("nomad-rundocker v0.1")
	if DEBUG:
	    printDic(os.environ)
	main(buildNumber)
    except KeyError:
	print("UNABLE to find key, current environment is:")
	printDic(os.environ)
	raise
