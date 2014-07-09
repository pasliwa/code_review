prd:
	/sbin/service ci stop
	cp init.d/jenkins /etc/init.d/jenkins
	cp init.d/ci /etc/init.d/ci
	cp config.py.prod config.py
	rm config.pyc
	/sbin/service ci start

dev:
	cp config.py.dev config.py
	rm config.pyc

tst:
	/sbin/service ci_test stop
	cp init.d/jenkins_test /etc/init.d/jenkins_test
	cp init.d/ci_test /etc/init.d/ci_test
	cp config.py.test config.py
	rm config.pyc
	/sbin/service ci_test start

