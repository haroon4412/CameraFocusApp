import paho.mqtt.client as mqtt
import threading
import json
import time
import socket
from settings import *

class Mosquito34:
    def __init__(self, skip = False):
        self.skip = skip
        self.pathTopic = mqtt_topics['pathTopic']
        self.dataTopic = mqtt_topics['dataTopic']
        self.manTopic = mqtt_topics['manTopic']
        self.healthTopic = mqtt_topics['healthTopic']
        self.manUpdateTopic = mqtt_topics['manUpdateTopic']
        self.rollBackTopic = mqtt_topics['rollBackTopic']
        self.prev_maneuver = 0
        self.mqtt_status = ''
        self.udp_port = 4454
        self.multicast_group = '239.0.0.1'  # Multicast IP address
        if not self.skip:
            self.udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            # Set multicast TTL (time to live) to control packet scope
            ttl = 2  # 1=same subnet, 2=same site, 32=same region, 255=global
            self.udp_socket.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, ttl)
            self.mqtt_th = threading.Thread(target=self.setup_mqtt)
            self.mqtt_application_running = True
            self.mqtt_th.start()

    def on_connect(self, client, userdata, flags, rc):
        if not self.skip:
            print("Connected with result code "+str(rc))
            ## if you want to send message once the node connected to the broker
            PathMSG = {"path":__file__}
            pathMSG = json.dumps(PathMSG, sort_keys=True)
            pathPacket = pathMSG.encode(encoding='UTF-8',errors='strict')
            client.publish(self.pathTopic,pathPacket,qos=2) # punlish file path at startup
            client.subscribe("spts/test/started")
            client.subscribe("spts/test/ended")
            print(self.pathTopic,pathPacket)
            
    def on_disconnect(self, client, userdata, rc):
        if not self.skip and rc != 0:
            self.mqtt_status = "mqtt disconnected"
            while True:
                try:
                    self.mqtt_client.reconnect()
                    self.mqtt_status = ''
                    print("Reconnected to mqtt")
                    break
                except:
                    print("Reconnecting failed, trying again")
                    time.sleep(5)

    def on_message(self, client, userdata, msg):
        if not self.skip:
            if msg.topic == "spts/test/started":
                self.startTrigger = True
                print("startTrigger:", self.startTrigger)
            if msg.topic == "spts/test/ended":
                self.startTrigger = False
                print("startTrigger:", self.startTrigger)

    def setup_mqtt(self):
        if not self.skip:
            self.mqtt_client = mqtt.Client()
            self.mqtt_client.on_connect = self.on_connect
            self.mqtt_client.on_disconnect = self.on_disconnect
            self.mqtt_client.on_message = self.on_message
            self.mqtt_client.connect('127.0.0.1', 1883, 60)
            while self.mqtt_application_running:
                self.mqtt_client.loop()
                time.sleep(1)

    def mqtt_health_publish(self, comming_message = ''):
        if not self.skip:
            message = {
                'alive': True,
                'exception': comming_message + self.mqtt_status
            }
            dataMsg = json.dumps(message)
            dataPacket = dataMsg.encode(encoding='UTF-8',errors='strict')
            self.mqtt_client.publish(self.healthTopic, dataPacket)


    def mqtt_publish(self, cross = False, center = False, front_entry = False, maneuver = 0, direction = 0, direction_distance = 0, slot_id = 0, inside = False):
        if not self.skip:
            rollback_distance = 0
            if direction == -1:
                rollback_distance = direction_distance
            OutMsg = {'cross':str(cross).lower(), 'center': str(center).lower(), 'inside': str(inside).lower(), 'bump':str(False).lower(), 'roll_back_distance': float(rollback_distance), \
                      'front_entry': str(front_entry).lower(), 'slot_id': str(slot_id).lower(),'LSTimestamp': int(time.time()*1000)}
            dataMsg = json.dumps(OutMsg, sort_keys=True)
            dataPacket = dataMsg.encode(encoding='UTF-8',errors='strict')
            self.mqtt_client.publish(self.dataTopic, dataPacket)
            try:
                self.udp_socket.sendto(dataPacket, (self.multicast_group, self.udp_port))
            except:
                pass

            dataMsg = json.dumps(maneuver)
            dataPacket = dataMsg.encode(encoding='UTF-8',errors='strict')
            self.mqtt_client.publish(self.manTopic,dataPacket)

            if maneuver == 0:
                self.prev_maneuver = 0
            elif self.prev_maneuver != maneuver:
                self.prev_maneuver = maneuver
                OutMsg = maneuver_messages_v2[maneuver]
                dataMsg = json.dumps(OutMsg, sort_keys=True)
                dataPacket = dataMsg.encode(encoding='UTF-8',errors='strict')
                self.mqtt_client.publish(self.manUpdateTopic, dataPacket)

