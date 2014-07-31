#!/bin/bash

kill -TERM `ps -f -u $UID | grep "jenkins.war" | grep -v grep | awk '{ print $2 }'`
