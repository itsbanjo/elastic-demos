import json
import time
import random
import os
from kafka import KafkaProducer
from datetime import datetime, timezone
import logging
import threading
from dataclasses import dataclass
from typing import List, Dict, Any

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

@dataclass
class SiteConfig:
    site_id: str
    display_name: str
    lat: float
    lon: float
    customers: List[str]
    message_frequency: float

class ICCPMessageGenerator:
    
    def __init__(self, site_config: SiteConfig):
        self.site_config = site_config
        self.message_counter = 0
        
    def generate_status_point_message(self, customer: str) -> Dict[str, Any]:
        self.message_counter += 1
        
        return {
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'site_id': self.site_config.site_id,
            'site_name': self.site_config.display_name,
            'customer_id': customer,
            'message_type': 'STATUS_POINT',
            'iccp_association': f'{self.site_config.site_id}-{customer}-01',
            'data': {
                'point_id': f'CB_{random.choice(["330", "220", "110"])}_L{random.randint(1,4)}_STATUS',
                'point_name': f'Circuit Breaker {random.choice(["330kV", "220kV", "110kV"])} Line {random.randint(1,4)}',
                'value': random.choice([0, 1]),
                'quality': random.choices(['GOOD', 'UNCERTAIN', 'INVALID'], weights=[92, 6, 2])[0],
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'change_counter': random.randint(1000, 9999)
            },
            'location': {
                'lat': self.site_config.lat,
                'lon': self.site_config.lon,
                'region': self.site_config.site_id.split('_')[0]
            },
            'metadata': {
                'protocol_version': 'IEC60870-6-503',
                'message_size': random.randint(128, 512),
                'association_active': random.choices([True, False], weights=[98, 2])[0],
                'roundtrip_time_ms': random.randint(5, 25),
                'message_number': self.message_counter
            }
        }
    
    def generate_analog_value_message(self, customer: str) -> Dict[str, Any]:
        self.message_counter += 1
        
        return {
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'site_id': self.site_config.site_id,
            'site_name': self.site_config.display_name,
            'customer_id': customer,
            'message_type': 'ANALOG_VALUE',
            'iccp_association': f'{self.site_config.site_id}-{customer}-01',
            'data': {
                'point_id': f'MW_{random.choice(["GEN", "LOAD", "FLOW"])}_L{random.randint(1,4)}',
                'point_name': f'{random.choice(["Generation", "Load", "Power Flow"])} MW Line {random.randint(1,4)}',
                'value': round(random.uniform(50.0, 500.0), 2),
                'quality': random.choices(['GOOD', 'UNCERTAIN', 'INVALID'], weights=[94, 5, 1])[0],
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'units': 'MW'
            },
            'location': {
                'lat': self.site_config.lat,
                'lon': self.site_config.lon,
                'region': self.site_config.site_id.split('_')[0]
            },
            'metadata': {
                'protocol_version': 'IEC60870-6-503',
                'message_size': random.randint(128, 512),
                'association_active': True,
                'roundtrip_time_ms': random.randint(5, 25),
                'message_number': self.message_counter
            }
        }
    
    def generate_protection_event_message(self, customer: str) -> Dict[str, Any]:
        self.message_counter += 1
        
        return {
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'site_id': self.site_config.site_id,
            'site_name': self.site_config.display_name,
            'customer_id': customer,
            'message_type': 'PROTECTION_EVENT',
            'iccp_association': f'{self.site_config.site_id}-{customer}-01',
            'data': {
                'event_id': f'PROT_EVT_{random.randint(10000, 99999)}',
                'event_type': random.choice(['OVERCURRENT', 'UNDERVOLTAGE', 'FREQUENCY_DEVIATION', 'LINE_FAULT']),
                'severity': random.choices(['LOW', 'MEDIUM', 'HIGH', 'CRITICAL'], weights=[40, 35, 20, 5])[0],
                'cleared': random.choices([True, False], weights=[85, 15])[0],
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'equipment_affected': f'Line {random.randint(1,4)}'
            },
            'location': {
                'lat': self.site_config.lat,
                'lon': self.site_config.lon,
                'region': self.site_config.site_id.split('_')[0]
            },
            'metadata': {
                'protocol_version': 'IEC60870-6-503',
                'message_size': random.randint(200, 600),
                'association_active': True,
                'roundtrip_time_ms': random.randint(8, 30),
                'message_number': self.message_counter
            }
        }

class ICCPSimulator:
    
    def __init__(self):
        self.kafka_brokers = os.environ.get('KAFKA_BROKERS', 'localhost:9092')
        self.site_name = os.environ.get('SITE_NAME', 'auckland-penrose')
        self.pod_name = os.environ.get('POD_NAME', 'unknown')
        
        self.site_config = self.load_site_config()
        
        self.message_generator = ICCPMessageGenerator(self.site_config)
        
        self.producer = self.create_kafka_producer()
        
        self.message_types = ['STATUS_POINT', 'ANALOG_VALUE', 'PROTECTION_EVENT', 'ENERGY_ACCOUNTING']
        self.type_weights = [50, 30, 15, 5]
        
        logger.info(f"🏗️ ICCP Simulator initialized for {self.site_config.display_name}")
        logger.info(f"📡 Kafka brokers: {self.kafka_brokers}")
        logger.info(f"🏢 Customers: {self.site_config.customers}")
        logger.info(f"⏱️ Message frequency: {self.site_config.message_frequency}s")
        
    def load_site_config(self) -> SiteConfig:
        sites_config = {
            "auckland-penrose": SiteConfig(
                site_id="AKL_PENROSE",
                display_name="Auckland Penrose 330kV",
                lat=-36.8485, lon=174.7633,
                customers=["CONTACT_ENERGY", "MERCURY_ENERGY", "GENESIS_ENERGY"],
                message_frequency=1.5
            ),
            "wellington-central": SiteConfig(
                site_id="WLG_CENTRAL",
                display_name="Wellington Central 220kV", 
                lat=-41.2865, lon=174.7762,
                customers=["MERCURY_ENERGY", "GENESIS_ENERGY"],
                message_frequency=2.0
            ),
            "christchurch-addington": SiteConfig(
                site_id="CHC_ADDINGTON",
                display_name="Christchurch Addington 66kV",
                lat=-43.5321, lon=172.6362,
                customers=["MERIDIAN_ENERGY", "CONTACT_ENERGY"],
                message_frequency=1.8
            ),
            "huntly-power": SiteConfig(
                site_id="HUNTLY_POWER",
                display_name="Huntly Power Station",
                lat=-37.5483, lon=175.0681,
                customers=["GENESIS_ENERGY"],
                message_frequency=0.8
            ),
            "manapouri-power": SiteConfig(
                site_id="MANAPOURI_POWER",
                display_name="Manapouri Power Station",
                lat=-45.5361, lon=167.1761,
                customers=["MERIDIAN_ENERGY"],
                message_frequency=1.0
            )
        }
        
        return sites_config.get(self.site_name, sites_config["auckland-penrose"])
    
    def create_kafka_producer(self) -> KafkaProducer:
        return KafkaProducer(
            bootstrap_servers=self.kafka_brokers,
            value_serializer=lambda x: json.dumps(x, default=str).encode('utf-8'),
            retry_backoff_ms=1000,
            retries=5,
            acks='all',
            compression_type='none'
        )
    
    def send_message(self, message: Dict[str, Any]):
        message_type = message['message_type']
        topic_map = {
            'STATUS_POINT': 'iccp-status-points',
            'ANALOG_VALUE': 'iccp-analog-values', 
            'PROTECTION_EVENT': 'iccp-protection-events',
            'ENERGY_ACCOUNTING': 'iccp-energy-accounting'
        }
        
        topic = topic_map.get(message_type, 'iccp-status-points')
        
        try:
            future = self.producer.send(topic, message)
            logger.debug(f"📤 Sent {message_type} to {topic}")
        except Exception as e:
            logger.error(f"❌ Failed to send message: {e}")
    
    def generate_and_send_message(self):
        customer = random.choice(self.site_config.customers)
        message_type = random.choices(self.message_types, weights=self.type_weights)[0]
        
        if message_type == 'STATUS_POINT':
            message = self.message_generator.generate_status_point_message(customer)
        elif message_type == 'ANALOG_VALUE':
            message = self.message_generator.generate_analog_value_message(customer)
        elif message_type == 'PROTECTION_EVENT':
            message = self.message_generator.generate_protection_event_message(customer)
        else:
            message = self.message_generator.generate_status_point_message(customer)
        
        self.send_message(message)
        
        logger.info(f"📡 [{message['timestamp'][:19]}] {message_type} → {customer} | Msg #{message['metadata']['message_number']}")
        
    def run_simulation(self):
        logger.info(f"🚀 Starting ICCP simulation for {self.site_config.display_name}")
        
        while True:
            try:
                self.generate_and_send_message()
                
                sleep_time = self.site_config.message_frequency + random.uniform(-0.3, 0.3)
                time.sleep(max(0.5, sleep_time))
                
            except KeyboardInterrupt:
                logger.info("🛑 Simulation stopped by user")
                break
            except Exception as e:
                logger.error(f"❌ Error in simulation loop: {e}")
                time.sleep(5)
        
        self.producer.close()
        logger.info("✅ ICCP Simulator shutdown complete")

def main():
    simulator = ICCPSimulator()
    simulator.run_simulation()

if __name__ == "__main__":
    main()