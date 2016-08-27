#!/usr/bin/python -u
"""
nomad docker doesn't allow us to do volumes, which hurts.
This is a work-around.  I hope they get their act together soon.

all META keys are capitalized by NOMAD, so be sure to define your _LABELS as uppercase.

required keys:
IMAGE -- name of the docker image to pull.

optional:
REGISTRY_URL = the URL for the regitry to pull from.
REGISTRY_USER = username for registry, defaults None
REGISTRY_PASSWORD = password for registry, defaults None
NETWORK_MODE = "bridge" network mode for docker:
    ('bridge': creates a new network stack for the container on the Docker bridge, 'none': no networking for this container, 'container:[name|id]': reuses another container network stack, 'host': use the host network stack inside the container or any name that identifies an existing Docker network).
	defaults "bridge"

nomad do HOST export networking at all, so you have to specify it special in the env {} config.
NETWORK_LABELS = "" space seperated list of network labels.
NOMAD_PORT_<label> = '' IP port to expose inside the container.
NOMAD_IP_<label> = '' IP ADDRESS to expose.

NOMAD_HOST_PORT_<label> = '' IP port to expose on the host.

nomad doesn't do volumes at all. currently only bind mounts are supported. here is how to do them:
VOLUME_LABELS="" is a space seperated list of volume labels (just like network labels)
SRC_<LABEL>=""  the source of the volume.
DST_<LABEL>="" the destination of the volume.
MODE_<LABEL>="" the mode (rw/ro) of the volume.  if missing defaults to rw.
"""

from __future__ import print_function
import os
import signal
import sys

try:
    from docker import Client
except ImportError:
    print("You must install docker-py module, try running: pip install docker-py")

#used for signal, yes globals suck, get over it.
RUNNINGID=0
DEBUG=True

def getKey(name, default=None):
    """get key or set default from os.environ, which is ""
    """
    if os.environ.has_key(name):
	ret = os.environ[name]
    else:
	ret = default
    return ret

def main(buildNumber):
    """main code"""
    global RUNNINGID
    cli = Client(base_url='unix://var/run/docker.sock')
    # specify the network mode, port bindings, and volume mounts.
    # this is how the docker python client wants these parameters
    networkMode = getKey('NOMAD_META_NETWORK_MODE', "bridge")
    networkLabels = getKey('NOMAD_META_NETWORK_LABELS', "")
    portBindings = {}
    for label in networkLabels.split():
	port = getKey('NOMAD_PORT_{}'.format(label))
	ip = getKey('NOMAD_IP_{}'.format(label))
	hostPort = getKey('NOMAD_HOST_PORT_{}'.format(label))
	portBindings[port] = (ip, hostPort)
	print("exposing container port {} to external ip:port {}:{}".format(port, ip, hostPort))
    volumeLabels = getKey('NOMAD_META_VOLUME_LABELS', "")
    volumes = {}
    for label in volumeLabels.split():
	src = os.environ['NOMAD_META_SRC_{}'.format(label)]
	dst = os.environ['NOMAD_META_DST_{}'.format(label)]
	mode = getKey('NOMAD_META_MODE_{}'.format(label), "rw")
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
		    binds=volumes, network_mode=networkMode)
    serviceName = os.environ['NOMAD_META_IMAGE']
    dockerName = "{}-{}".format(serviceName, os.environ['NOMAD_ALLOC_ID'])
    registryURL = getKey('NOMAD_META_REGISTRY_URL', "")
    registryAuthConfig = {
	'username': getKey('NOMAD_META_REGISTRY_USER'),
	'password': getKey('NOMAD_META_REGISTRY_PASSWORD')
	}
    imageTag = buildNumber
    registry = '%s%s' % (registryURL, serviceName)
    image = "{}:{}".format(registry, imageTag)
    print("will download image {}:{}".format(registry, imageTag))
    cli.pull(repository=registry, tag=imageTag, stream=False, auth_config=registryAuthConfig)
    containers = cli.containers(all=True,filters={'name':image})
    # if container name or image is already around, stop and remove it, since we are about to run it again.
    for i in containers:
	if i['Image'] == image:
	    # currently running, we should stop it.
	    if i['State'] == 'running':
		print("stoppping container {} with ID {}".format(i['Image'], i['Id']))
		cli.stop(i['Id'])
		cli.remove_container(i['Id'])
	    else:
		print('container {} exists, but is not running, removing id {}'.format(i['Image'], i['Id']))
		cli.remove_container(i['Id'])
	if dockerName in i['Names']:
	    if i['State'] == 'running':
		print("stoppping container {} with ID {}".format(i['Image'], i['Id']))
		cli.stop(i['Id'])
		cli.remove_container(i['Id'])
	    else:
		print('container {} exists, but is not running, removing id {}'.format(i['Image'], i['Id']))
		cli.remove_container(i['Id'])
    container = cli.create_container(image=image, detach=True, name=dockerName,
                                     environment=labels, labels=labels,
				     ports=portBindings.keys(), host_config=hostConfig)
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

def printEnv(d):
    """for printing os.environ, pprint doesn't do it well *sad face*
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
	    printEnv(os.environ)
	main(buildNumber)
    except KeyError:
	print("UNABLE to find key, current environment is:")
	printEnv(os.environ)
	raise
