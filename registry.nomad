# There can only be a single job definition per file.
# Create a job with ID and Name 'example'
job "registry" {
	# Run the job in the global region, which is the default.
	# region = "global"

	# Specify the datacenters within the region this job can run in.
	datacenters = ["dc1"]

	# Service type jobs optimize for long-lived services. This is
	# the default but we can change to batch for short-lived tasks.
	# type = "service"

	# Priority controls our access to resources and scheduling priority.
	# This can be 1 to 100, inclusively, and defaults to 50.
	# priority = 50

	# Restrict our job to only linux. We can specify multiple
	# constraints as needed.
	constraint {
		attribute = "${attr.kernel.name}"
		value = "linux"
	}
	constraint {
		attribute = "${node.unique.name}"
		regexp = "docker"
	}

	# Configure the job to do rolling updates
	update {
		# Stagger updates every 10 seconds
		stagger = "10s"

		# Update a single task at a time
		max_parallel = 1
	}

	# Create a 'cache' group. Each task in the group will be
	# scheduled onto the same machine.
	group "registry" {
		# Control the number of instances of this groups.
		# Defaults to 1
		# count = 1

		# Configure the restart policy for the task group. If not provided, a
		# default is used based on the job type.
		restart {
			# The number of attempts to run the job within the specified interval.
			attempts = 10
			interval = "5m"
			
			# A delay between a task failing and a restart occurring.
			delay = "25s"

			# Mode controls what happens when a task has restarted "attempts"
			# times within the interval. "delay" mode delays the next restart
			# till the next interval. "fail" mode does not restart the task if
			# "attempts" has been hit within the interval.
			mode = "delay"
		}

		# Define a task to run
		task "registry" {
			# Use Docker to run the task.
			driver = "raw_exec"

			# Configure Docker driver with the image
			config {
				command = "/usr/local/bin/runNomadDocker.py"
				args = [
				"2"
				]
				}
			meta {
				IMAGE = "registry"
				NETWORK_LABELS = "http"
				# ALL meta keys get capitalized regardless of what you put here..
				VOLUME_LABELS = "AUTH DATA CERTS"
				SRC_data = "/docker/registry/data"
				DST_data = "/var/lib/registry"
				SRC_certs = "/docker/registry/certs"
				DST_certs = "/certs"
				SRC_auth = "/docker/registry/auth"
				DST_auth = "/auth"
				REGISTRY_HTTP_TLS_CERTIFICATE = "/certs/server.crt"
				REGISTRY_HTTP_TLS_KEY = "/certs/server.key"
				REGISTRY_AUTH = "htpasswd"
				REGISTRY_AUTH_HTPASSWD_PATH = "/auth/htpasswd"
				REGISTRY_AUTH_HTPASSWD_REALM = "Registry Realm"
			}
			env {
					NOMAD_HOST_PORT_http = "5000"
				}
			service {
				name = "nomad-registry"
				tags = ["global", "cache"]
				port = "http"
				check {
					name = "alive"
					type = "tcp"
					interval = "10s"
					timeout = "2s"
				}
			}

			# We must specify the resources required for
			# this task to ensure it runs on a machine with
			# enough capacity.
			resources {
				cpu = 500 # 500 Mhz
				memory = 256 # 256MB
				network {
					mbits = 1
					port "http" {
						static = 5000
					}
				}
			}

			# The artifact block can be specified one or more times to download
			# artifacts prior to the task being started. This is convenient for
			# shipping configs or data needed by the task.
			# artifact {
			#	  source = "http://foo.com/artifact.tar.gz"
			#	  options {
			#	      checksum = "md5:c4aa853ad2215426eb7d70a21922e794"
			#     }
			# }
			
			# Specify configuration related to log rotation
			# logs {
			#     max_files = 10
			#	  max_file_size = 15
			# }
			 
			# Controls the timeout between signalling a task it will be killed
			# and killing the task. If not set a default is used.
			# kill_timeout = "20s"
		}
	}
}
