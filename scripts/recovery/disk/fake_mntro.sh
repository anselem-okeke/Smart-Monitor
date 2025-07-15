#!/bin/bash

sudo mkdir /mnt/test_ro
sudo dd if=/dev/zero of=/tmp/testfs.img bs=10M count=10
mkfs.ext4 /tmp/testfs.img
sudo mount -o loop /tmp/testfs.img /mnt/test_ro
sudo mount -o remount,ro /mnt/test_ro
