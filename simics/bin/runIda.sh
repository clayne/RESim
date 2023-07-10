#!/bin/bash
#
# Start IDA for a given target, setting a hotkey of "R" to attach to 
# the debugger and load the RESim IDA Client plugin. 
#
# The target file (to be disassembled) must be the first argument.
# Options for the 2nd argument include:
#     color -- reset IDA graph block colors and then color per the program hits files
#     reset -- just reset
#     remote -- remote host name for copying hits files.  TBD launch ssh tunnel if needed.
#
if [ -z "$IDA_DIR" ]; then
    echo "IDA_DIR not defined."
    exit
fi
if [ -z "$RESIM_DIR" ]; then
    echo "RESIM_DIR not defined."
    exit
fi
if [ -z "$RESIM_IDA_DATA" ]; then
    echo "RESIM_IDA_DATA not defined."
    exit
fi
cp -u $RESIM_DIR/simics/ida/runRESim.idc $IDA_DIR/idc
if [ $# -eq 0 ] || [ $1 = "-h" ]; then
    echo "runIda.sh [-64] <target> [color/reset] [server]"
    exit
fi
ida_suffix=idb
idacmd=$IDA_DIR/ida
if [[ "$1" == "-64" ]]; then
   echo "is 64"
   idacmd=$IDA_DIR/ida64
   ida_suffix=i64
   shift 1
fi
target=$1
echo "target is $1"
target_base="$(basename -- $target)"
here="$(pwd)"
root_dir="$(basename --  $here)"
old_dir=$RESIM_IDA_DATA/$target_base
new_dir=$RESIM_IDA_DATA/$root_dir/$target_base
if [[ -d $old_dir ]] && [[ ! -d $new_dir ]]; then
    echo "Sorry, paths relative to RESIM_IDA_DATA have changed."
    echo "Also, runIda.sh assumes you are running from the file system root (per your ini file)."
    echo "If $old_dir is where the ida data is, rename it to $new_dir"
    echo "Or, if $old_dir is from some other system, fix its path, change its name, or remove it."
    exit
fi
resim_ida_arg=""
#
# syntax is runIDA.sy target [color/reset] [server]
#
shift 1
if [ $# -gt 1 ];then
    echo "more than 1"
    remote=$2
    resim_ida_arg=$1
else
    if [ "$1" == color ] || [ "$1" == reset ]; then
       resim_ida_arg=$1
    else
       remote=$1
    fi
fi    
if [ "$resim_ida_arg" == color ] && [ ! -z $remote ]; then
       remote_ida=$( ssh $remote "source $HOME/.resimrc;mkdir -p \$RESIM_IDA_DATA/$root_dir/$target_base; echo \$RESIM_IDA_DATA" )
       if [ -z "$remote_ida" ];then
           echo "The $remote server needs a ~/.resimrc file containing the RESim env variables that may be in your ~/.bashrc file"
           exit 1 
       fi
       rsync -avh $remote:$remote_ida/$root_dir/$target_base/*.hits $RESIM_IDA_DATA/$root_dir/$target_base/
fi
if [ ! -z "$remote" ]; then
    echo "REMOTE IS $remote"
    tunnel=$( ps -aux | grep [9]123 )
    if [[ -z "$tunnel" ]];then
        echo "No tunnel found for $remote, create one."
        ssh -fN -L 9123:localhost:9123 -oStrictHOstKeyChecking=no -oUserKnownHostsFile=/dev/null $remote
    else
       if [[ "$tunnel" == *"$remote"* ]]; then
           echo "Tunnel to $remote found."
       else
           pid=$(echo $tunnel | awk '{print $2}')
           echo "Tunnel to wrong server found."
           echo "Will kill $pid and start new tunnel to $remote"
           kill $pid
           ssh -fN -L 9123:localhost:9123 -oStrictHOstKeyChecking=no -oUserKnownHostsFile=/dev/null $remote
       fi
    fi
fi

target_path=$(realpath $target)
ida_db_path=$RESIM_IDA_DATA/$root_dir/$target_base/$target_base.$ida_suffix

if [ -z "$IDA_ANALYSIS" ]; then
    export IDA_ANALYSIS=/mnt/resim_archive/analysis
fi
export ida_analysis_path=$IDA_ANALYSIS/$root_dir/$target_base
mkdir -p $ida_analysis_path

echo "target is $target"
echo "dbpath $ida_db_path"
echo "resim_ida_arg is $resim_ida_arg"
if [[ -f $ida_db_path ]];then
    #$idacmd -S"$RESIM_DIR/simics/ida/RESimHotKey.idc $target_path $@" $ida_db_path
    #echo "ida_db_path is $ida_db_path"
    export IDA_DB_PATH=$ida_db_path
    $idacmd -S"$RESIM_DIR/simics/ida/RESimHotKey.idc $resim_ida_arg" $ida_db_path
    #$idacmd -z10000 -L/tmp/ida.log -S"$RESIM_DIR/simics/ida/RESimHotKey.idc $resim_ida_arg" $ida_db_path
else
    echo "No IDA db at $ida_db_path  create it."
    mkdir -p $RESIM_IDA_DATA/$root_dir/$target_base
    $idacmd -o$ida_db_path -S"$RESIM_DIR/simics/ida/RESimHotKey.idc $target_path $@" $target
fi
