#!/bin/bash
#
# Run an ida script against a given target
#
if [ ! -z "$IDA_DUMP_DIR" ]; then
    IDA_DIR=$IDA_DUMP_DIR
    echo "Redefind IDA_DIR to $IDA_DIR"
fi
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
cp $RESIM_DIR/simics/ida/runRESim.idc $IDA_DIR/idc
if [[ $# -eq 0 ]] || [[ "$1" = "-h" ]]; then
    echo "idaThis.sh [-64] <program> <script>"
    echo "    Runs the given IDA script after loading the named program.
    exit
fi
ida_suffix=id0
idacmd=$IDA_DIR/idat
if [[ "$1" == "-64" ]]; then
   echo "is 64"
   idacmd=$IDA_DIR/ida64
   ida_suffix=i64
   shift 1
fi
target=$1
echo "target is $1"
target_base="$(basename -- "$target")"
echo "the target base is $target_base"
here="$(pwd)"
echo "we are currently: $here"
root_dir="$(basename --  "$here")"
echo "the root_dir is $root_dir"
old_dir=$RESIM_IDA_DATA/$target_base
new_dir=$RESIM_IDA_DATA/$root_dir/$target_base
if [[ -d $old_dir ]] && [[ ! -d $new_dir ]]; then
    echo "idaThis.sh assumes you are running from the file system root (per your ini file)."
    echo "If $old_dir is where the ida data is, rename it to $new_dir"
    echo "Or, if $old_dir is from some other system, fix its path, change its name, or remove it."
    exit
fi

if [ -z "$IDA_ANALYSIS" ]; then
    export IDA_ANALYSIS=/mnt/resim_eems/resim/archive/analysis
fi
if [[ $target = $here/* ]]; then
    target=$(realpath --relative-to="${PWD}" "$target")
    echo "full path given to runIda, truncate it to $target"
fi

export ida_target_path=$(realpath "$target")
ida_db_path=$RESIM_IDA_DATA/$root_dir/$target.$ida_suffix
other_ida_db_path=$RESIM_IDA_DATA/$root_dir/$target.idb
parent="$(dirname "$ida_db_path")"
mkdir -p "$parent"

export ida_analysis_path=$IDA_ANALYSIS/$root_dir/$target
mkdir -p "$ida_analysis_path"

if [[ ! -f $target ]]; then
    echo "***ERROR:   No file found at $target"
    exit 1
fi
echo "target is $target"

scriptname=$2
echo "dbpath $ida_db_path"
if [[ -f $ida_db_path ]] || [[ -f $other_ida_db_path ]];then
    export IDA_DB_PATH=$ida_db_path
    # Get image base from readelf / readpe and set an env with it and have idaThis do a rebase
    # using ida_segment.rebase_program(offset, MSF_FIXONCE) and exit WITHOUT saving db
    export target_image_base=$(readpe "$ida_target_path" 2>/dev/null | grep ImageBase | awk '{print$2}')
    if [ -z $target_image_base ]; then
        echo "read ELF header to get image base"
        export target_image_base=$(readelf -l "$ida_target_path" 2>/dev/null | grep -m1 LOAD | awk '{print $3}')
    fi
    if [ -z $target_image_base ]; then
        echo "No readelf available, will use image base per IDA database."
    else
        echo "image_base is $target_image_base"
    fi
    echo $idacmd -L/tmp/idaThis.log -A -a -S$RESIM_DIR/simics/ida/$scriptname $ida_db_path
    "$idacmd" -L/tmp/idaThis.log -A -S$RESIM_DIR/simics/ida/$scriptname "$ida_db_path" || tail /tmp/idaThis.log && exit 1
else
    echo "No IDA db at $ida_db_path  create it."
    mkdir -p "$RESIM_IDA_DATA/$root_dir/$target_base"
    echo $idacmd -L/tmp/idaThis.log -A -o"$ida_db_path" -S$RESIM_DIR/simics/ida/$scriptname "$target"
    "$idacmd" -L/tmp/idaThis.log -A -o"$ida_db_path" -S$RESIM_DIR/simics/ida/$scriptname "$target" || tail /tmp/idaThis.log && exit 1
    echo $idacmd -L/tmp/idaThis.log -A -o$ida_db_path -S$RESIM_DIR/simics/ida/$scriptname "$target"
fi
tail /tmp/idaThis.log
