#!/bin/bash

umask 0002
nohup nice $HOME/code_review/code_review.fcgi >$HOME/logs/code_review.out 2>&1 &
