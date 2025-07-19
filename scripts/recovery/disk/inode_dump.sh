#!/bin/bash
#for i in $(seq 1 100000); do
#  touch file_"$i"
#done

mkdir /tmp/inode_test
#mkdir -p /var/tmp/inode_dump10
# shellcheck disable=SC2164
#cd /var/tmp/inode_dump10
cd /tmp/inode_test
for d in {1..100}; do
  mkdir dir_"$d"
  for f in {1..1000}; do
    touch dir_"$d"/file_"$f"
  done
done

