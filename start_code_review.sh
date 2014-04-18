#!/bin/bash

umask 0002
nohup nice /home/ci_test/code_review/code_review.fcgi >/home/ci_test/logs/code_review.out 2>&1 &
