#!/bin/bash
#
# automated test of RESim using cadet01 sample.  
# Covers: ROP detection, reverseToSP, prepInjectWatch, injectIO with kernel buffer.
#
if [[ -z "$RESIM_DIR" ]]; then
    echo "RESIM_DIR not defined."
    exit
fi
if [[ ! -f /usr/bin/xdotool ]]; then
    echo "xdotool must be installed.  not found in /usr/bin"
    exit
fi
# use free simics so multiple afls can run
export SIMDIR=/mnt/resim_eems/resim/archive/simics6/free_install/simics-6.0.157
TD="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
rm -fr cadet-tst
mkdir cadet-tst
cd cadet-tst
resim-ws.sh
export WS=$RESIM_DIR/simics/workspace
echo "ws is $WS"
cp $WS/ubuntu_driver.ini $WS/ubuntu.param $WS/driver-script.sh $WS/mapdriver.simics $WS/client.py $WS/authorized_keys .


sed -i 's/mapdriver.simics/cadet.simics/' ubuntu_driver.ini
sed -i '/OS_TYPE/a AFL_STOP_ON_READ=TRUE' ubuntu_driver.ini
#echo "INTERACT_SCRIPT=teecadet.simics" >> ubuntu_driver.ini

cp $TD/*.simics .
cp $TD/*.sh .
cp $TD/*.directive .
cp $TD/*.io .
# use ~/bin/set-title to doxtool can find the window
$HOME/bin/set-title "cadet01-tst"

resim ubuntu_driver.ini -n || exit
# the above should have created a rop warning in the log.  check it.
./checkROP.sh || exit
./testTrack.sh || exit
./testAFL.sh 
./testPlay.sh || exit
./testDedupe.sh || exit
./testRunTrack.sh || exit

