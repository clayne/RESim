kill -9 $(ps aux | grep '[l]aunchRESim.py' | awk '{print $2}')
kill -9 $(ps aux | grep '[r]unAFL' | awk '{print $2}')
kill -9 $(ps aux | grep '[s]imics-common' | awk '{print $2}')
