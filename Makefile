prd:
	sudo /sbin/service ci stop || :
	sudo cp init.d/jenkins /etc/init.d/jenkins
	sudo cp init.d/ci /etc/init.d/ci
	cp jenkins/start-jenkins.sh.prod $(HOME)/jenkins/start-jenkins.sh
	cp jenkins/restart-jenkins.sh.prod $(HOME)/jenkins/restart-jenkins.sh
	cp jenkins/stop-jenkins.sh $(HOME)/jenkins/stop-jenkins.sh
	cp config.py.prod config.py
	rm config.pyc
	sudo /sbin/service ci start
	rm cron/crontab || :
	echo "30 1 * * * $(shell pwd)/cron/clear_kloTables" >> cron/crontab
	echo "00 0 * * * $(HOME)/jenkins/restart-jenkins.sh" >> cron/crontab
	crontab cron/crontab
	rm cron/crontab

dev:
	cp config.py.dev config.py
	rm config.pyc

tst:
	sudo /sbin/service ci_test stop || :
	sudo cp init.d/jenkins_test /etc/init.d/jenkins_test
	sudo cp init.d/ci_test /etc/init.d/ci_test
	cp jenkins/start-jenkins.sh.test $(HOME)/jenkins/start-jenkins.sh
	cp jenkins/restart-jenkins.sh.test $(HOME)/jenkins/restart-jenkins.sh
	cp jenkins/stop-jenkins.sh $(HOME)/jenkins/stop-jenkins.sh
	cp config.py.test config.py
	rm config.pyc
	sudo /sbin/service ci_test start
	rm cron/crontab || :
	echo "30 1 * * * $(shell pwd)/cron/clear_kloTables" >> cron/crontab
	echo "00 1 * * * $(HOME)/jenkins/restart-jenkins.sh" >> cron/crontab
	crontab cron/crontab
	rm cron/crontab

