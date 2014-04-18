#!/bin/bash

kill -TERM `ps -f -u $UID | grep "code_review.fcgi" | grep -v grep | awk '{ print $2 }'`
