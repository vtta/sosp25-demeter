#!/bin/bash
# set -eux

[ $EUID -eq 0 ] || {
  echo "Please run as root"
  exit
}

SELF="$(dirname "$(readlink -f "$0")")"
cd "$SELF"

name=virbr921
count=16
start() {
  systemctl --no-pager --full start libvirtd
  virsh net-define $name.xml || true
  virsh net-start $name || true
  for i in $(seq 0 $count); do
    local tap=ichb$i
    ip tuntap del $tap mode tap
    ip tuntap add $tap mode tap
    brctl addif $name $tap
    ip link set dev $tap up
  done
}

stop() {
  for i in $(seq 0 $count); do
    local tap=ichb$i
    ip tuntap del $tap mode tap
  done
  virsh net-destroy $name || true
  virsh net-undefine $name || true
}

usage() {
  echo "Usage:"
  echo "    $0 <-a|--start>"
  echo "    $0 <-d|--stop>"
  echo "    $0 <-r|--restart>"
  exit
}

# Call getopt to validate the provided input.
options=$(getopt -o adr --long start,stop,restart -- "$@")
[ $? -eq 0 ] || usage
eval set -- "$options"
while true; do
  case "$1" in
  -a | --start) start ;;
  -d | --stop) stop ;;
  -r | --restart) stop || true; start ;;
  --)
    shift
    break
    ;;
  *) usage ;;
  esac
  shift
done
