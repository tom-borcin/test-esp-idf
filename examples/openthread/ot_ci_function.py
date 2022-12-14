# SPDX-FileCopyrightText: 2022 Espressif Systems (Shanghai) CO LTD
# SPDX-License-Identifier: Unlicense OR CC0-1.0
# !/usr/bin/env python3
# this file defines some functions for testing cli and br under pytest framework

import re
import socket
import struct
import subprocess
import time
from typing import Tuple, Union

import netifaces
import pexpect
from pytest_embedded_idf.dut import IdfDut


def reset_thread(dut:IdfDut) -> None:
    dut.write(' ')
    dut.write('state')
    clean_buffer(dut)
    wait(dut, 1)
    dut.write('factoryreset')
    dut.expect('OpenThread attached to netif', timeout=20)
    dut.write(' ')
    dut.write('state')


# config thread
def config_thread(dut:IdfDut, model:str, dataset:str='0') -> Union[str, None]:
    if model == 'random':
        dut.write('dataset init new')
        dut.expect('Done', timeout=2)
        dut.write('dataset commit active')
        dut.expect('Done', timeout=2)
        dut.write('ifconfig up')
        dut.expect('Done', timeout=2)
        dut.write('dataset active -x')          # get dataset
        dut_data = dut.expect(r'\n(\w{212})\r', timeout=5)[1].decode()
        return str(dut_data)
    if model == 'appointed':
        tmp = 'dataset set active ' + str(dataset)
        dut.write(tmp)
        dut.expect('Done', timeout=2)
        dut.write('ifconfig up')
        dut.expect('Done', timeout=2)
        return None
    return None


# get the mleid address of the thread
def get_mleid_addr(dut:IdfDut) -> str:
    dut_adress = ''
    clean_buffer(dut)
    dut.write('ipaddr mleid')
    dut_adress = dut.expect(r'\n((?:\w+:){7}\w+)\r', timeout=5)[1].decode()
    return dut_adress


# get the rloc address of the thread
def get_rloc_addr(dut:IdfDut) -> str:
    dut_adress = ''
    clean_buffer(dut)
    dut.write('ipaddr rloc')
    dut_adress = dut.expect(r'\n((?:\w+:){7}\w+)\r', timeout=5)[1].decode()
    return dut_adress


# get the linklocal address of the thread
def get_linklocal_addr(dut:IdfDut) -> str:
    dut_adress = ''
    clean_buffer(dut)
    dut.write('ipaddr linklocal')
    dut_adress = dut.expect(r'\n((?:\w+:){7}\w+)\r', timeout=5)[1].decode()
    return dut_adress


# get the global unicast address of the thread:
def get_global_unicast_addr(dut:IdfDut, br:IdfDut) -> str:
    dut_adress = ''
    clean_buffer(br)
    br.write('br omrprefix')
    omrprefix = br.expect(r'\n((?:\w+:){4}):/\d+\r', timeout=5)[1].decode()
    clean_buffer(dut)
    dut.write('ipaddr')
    dut_adress = dut.expect(r'(%s(?:\w+:){3}\w+)\r' % str(omrprefix), timeout=5)[1].decode()
    return dut_adress


# start thread
def start_thread(dut:IdfDut) -> str:
    role = ''
    dut.write('thread start')
    tmp = dut.expect(r'Role detached -> (\w+)\W', timeout=20)[0]
    role = re.findall(r'Role detached -> (\w+)\W', str(tmp))[0]
    return role


def wait_key_str(leader:IdfDut, child:IdfDut) -> None:
    wait(leader, 1)
    leader.expect('OpenThread attached to netif', timeout=20)
    leader.write(' ')
    leader.write('state')
    child.expect('OpenThread attached to netif', timeout=20)
    child.write(' ')
    child.write('state')


def config_network(leader:IdfDut, child:IdfDut, leader_name:str, thread_dataset_model:str,
                   thread_dataset:str, wifi:IdfDut, wifi_ssid:str, wifi_psk:str) -> str:
    wait_key_str(leader, child)
    return form_network_using_manual_configuration(leader, child, leader_name, thread_dataset_model,
                                                   thread_dataset, wifi, wifi_ssid, wifi_psk)


# config br and cli manually
def form_network_using_manual_configuration(leader:IdfDut, child:IdfDut, leader_name:str, thread_dataset_model:str,
                                            thread_dataset:str, wifi:IdfDut, wifi_ssid:str, wifi_psk:str) -> str:
    reset_thread(leader)
    clean_buffer(leader)
    reset_thread(child)
    clean_buffer(child)
    leader.write('channel 12')
    leader.expect('Done', timeout=2)
    child.write('channel 12')
    child.expect('Done', timeout=2)
    res = '0000'
    if wifi_psk != '0000':
        res = connect_wifi(wifi, wifi_ssid, wifi_psk, 10)[0]
    leader_data = ''
    if thread_dataset_model == 'random':
        leader_data = str(config_thread(leader, 'random'))
    else:
        config_thread(leader, 'appointed', thread_dataset)
    if leader_name == 'br':
        leader.write('bbr enable')
        leader.expect('Done', timeout=2)
    role = start_thread(leader)
    assert role == 'leader'
    if thread_dataset_model == 'random':
        config_thread(child, 'appointed', leader_data)
    else:
        config_thread(child, 'appointed', thread_dataset)
    if leader_name != 'br':
        child.write('bbr enable')
        child.expect('Done', timeout=2)
    role = start_thread(child)
    assert role == 'child'
    wait(leader, 10)
    return res


# ping of thread
def ot_ping(dut:IdfDut, target:str, times:int) -> Tuple[int, int]:
    command = 'ping ' + str(target) + ' 0 ' + str(times)
    dut.write(command)
    transmitted = dut.expect(r'(\d+) packets transmitted', timeout=30)[1].decode()
    tx_count = int(transmitted)
    received = dut.expect(r'(\d+) packets received', timeout=30)[1].decode()
    rx_count = int(received)
    return tx_count, rx_count


# connect Wi-Fi
def connect_wifi(dut:IdfDut, ssid:str, psk:str, nums:int) -> Tuple[str, int]:
    clean_buffer(dut)
    ip_address = ''
    information = ''
    for order in range(1, nums):
        dut.write('wifi connect -s ' + str(ssid) + ' -p ' + str(psk))
        tmp = dut.expect(pexpect.TIMEOUT, timeout=5)
        if 'sta ip' in str(tmp):
            ip_address = re.findall(r'sta ip: (\w+.\w+.\w+.\w+),', str(tmp))[0]
        information = dut.expect(r'wifi sta (\w+ \w+ \w+)\W', timeout=5)[1].decode()
        if information == 'is connected successfully':
            break
    assert information == 'is connected successfully'
    return ip_address, order


def reset_host_interface() -> None:
    interface_name = get_host_interface_name()
    flag = False
    try:
        command = 'ifconfig ' + interface_name + ' down'
        subprocess.call(command, shell=True, timeout=5)
        time.sleep(1)
        command = 'ifconfig ' + interface_name + ' up'
        subprocess.call(command, shell=True, timeout=10)
        time.sleep(1)
        flag = True
    finally:
        time.sleep(1)
        assert flag


def set_interface_sysctl_options() -> None:
    interface_name = get_host_interface_name()
    flag = False
    try:
        command = 'sysctl -w net/ipv6/conf/' + interface_name + '/accept_ra=2'
        subprocess.call(command, shell=True, timeout=5)
        time.sleep(1)
        command = 'sysctl -w net/ipv6/conf/' + interface_name + '/accept_ra_rt_info_max_plen=128'
        subprocess.call(command, shell=True, timeout=5)
        time.sleep(1)
        flag = True
    finally:
        time.sleep(2)
        assert flag


def init_interface_ipv6_address() -> None:
    interface_name = get_host_interface_name()
    flag = False
    try:
        command = 'ip -6 route | grep ' + interface_name + " | grep ra | awk {'print $1'} | xargs -I {} ip -6 route del {}"
        subprocess.call(command, shell=True, timeout=5)
        time.sleep(0.5)
        subprocess.call(command, shell=True, timeout=5)
        time.sleep(1)
        command = 'ip -6 address show dev ' + interface_name + \
            " scope global | grep 'inet6' | awk {'print $2'} | xargs -I {} ip -6 addr del {} dev " + interface_name
        subprocess.call(command, shell=True, timeout=5)
        time.sleep(1)
        flag = True
    finally:
        time.sleep(1)
        assert flag


def get_host_interface_name() -> str:
    interfaces = netifaces.interfaces()
    interface_name = [s for s in interfaces if 'wl' in s][0]
    return str(interface_name)


def clean_buffer(dut:IdfDut) -> None:
    str_length = str(len(dut.expect(pexpect.TIMEOUT, timeout=0.1)))
    dut.expect(r'[\s\S]{%s}' % str(str_length), timeout=10)


def check_if_host_receive_ra(br:IdfDut) -> bool:
    interface_name = get_host_interface_name()
    clean_buffer(br)
    br.write('br omrprefix')
    omrprefix = br.expect(r'\n((?:\w+:){4}):/\d+\r', timeout=5)[1].decode()
    command = 'ip -6 route | grep ' + str(interface_name)
    out_str = subprocess.getoutput(command)
    print('br omrprefix: ', str(omrprefix))
    print('host route table:\n', str(out_str))
    return str(omrprefix) in str(out_str)


def host_connect_wifi() -> None:
    command = '. /home/test/wlan_connection_OTTE.sh'
    subprocess.call(command, shell=True, timeout=30)
    time.sleep(5)


def is_joined_wifi_network(br:IdfDut) -> bool:
    return check_if_host_receive_ra(br)


thread_ipv6_group = 'ff04:0:0:0:0:0:0:125'


def check_ipmaddr(dut:IdfDut) -> bool:
    clean_buffer(dut)
    dut.write('ipmaddr')
    info = dut.expect(pexpect.TIMEOUT, timeout=2)
    if thread_ipv6_group in str(info):
        return True
    return False


def thread_is_joined_group(dut:IdfDut) -> bool:
    command = 'mcast join ' + thread_ipv6_group
    dut.write(command)
    dut.expect('Done', timeout=2)
    order = 0
    while order < 3:
        if check_ipmaddr(dut):
            return True
        dut.write(command)
        wait(dut, 2)
        order = order + 1
    return False


host_ipv6_group = 'ff04::125'


def host_joined_group() -> bool:
    interface_name = get_host_interface_name()
    command = 'netstat -g | grep ' + str(interface_name)
    out_str = subprocess.getoutput(command)
    print('groups:\n', str(out_str))
    return host_ipv6_group in str(out_str)


class udp_parameter:

    def __init__(self, group:str='', try_join_udp_group:bool=False, timeout:float=15.0, udp_bytes:bytes=b''):
        self.group = group
        self.try_join_udp_group = try_join_udp_group
        self.timeout = timeout
        self.udp_bytes = udp_bytes


def create_host_udp_server(myudp:udp_parameter) -> None:
    interface_name = get_host_interface_name()
    try:
        print('The host start to create udp server!')
        if_index = socket.if_nametoindex(interface_name)
        sock = socket.socket(socket.AF_INET6, socket.SOCK_DGRAM)
        sock.bind(('::', 5090))
        sock.setsockopt(
            socket.IPPROTO_IPV6, socket.IPV6_JOIN_GROUP,
            struct.pack('16si', socket.inet_pton(socket.AF_INET6, myudp.group),
                        if_index))
        myudp.try_join_udp_group = True
        sock.settimeout(myudp.timeout)
        print('The host start to receive message!')
        myudp.udp_bytes = (sock.recvfrom(1024))[0]
        print('The host has received message: ', myudp.udp_bytes)
    except socket.error:
        print('The host did not receive message!')
    finally:
        print('Close the socket.')
        sock.close()


def wait(dut:IdfDut, wait_time:float) -> None:
    dut.expect(pexpect.TIMEOUT, timeout=wait_time)
