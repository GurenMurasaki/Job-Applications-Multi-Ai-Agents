"""
Kafka Consumer for Job Offers

Consumes job offer messages from Kafka topics.
Handles multiple topics for different job sources (LinkedIn, Indeed, etc.)
"""

import json
from typing import Iterator, Dict, Any, Optional, List
from loguru import logger

try:
    from kafka import KafkaConsumer
    from kafka.errors import KafkaError
    KAFKA_AVAILABLE = True
except ImportError:
    KAFKA_AVAILABLE = False
    logger.warning("kafka-python not installed. Kafka functionality disabled.")


class JobKafkaConsumer:
    """
    Kafka consumer for job offer messages.
    
    Consumes messages from configured topics until timeout
    (indicating no more messages available).
    """
    
    def __init__(self, config: dict):
        """
        Initialize the Kafka consumer.
        
        Args:
            config: Kafka configuration dictionary
        """
        self.config = config
        self.bootstrap_servers = config.get("bootstrap_servers", "localhost:9092")
        self.group_id = config.get("group_id", "job-application-agents")
        self.topics = config.get("topics", ["linkedin-jobs"])
        self.timeout_ms = config.get("consumer_timeout_ms", 30000)
        self.auto_offset_reset = config.get("auto_offset_reset", "earliest")
        
        self.consumer: Optional[Any] = None
        self._connected = False
    
    def _connect(self):
        """Establish connection to Kafka."""
        if not KAFKA_AVAILABLE:
            logger.error("Kafka library not available")
            return False
        
        if self._connected:
            return True
        
        try:
            self.consumer = KafkaConsumer(
                *self.topics,
                bootstrap_servers=self.bootstrap_servers,
                group_id=self.group_id,
                auto_offset_reset=self.auto_offset_reset,
                enable_auto_commit=True,
                value_deserializer=lambda m: json.loads(m.decode('utf-8')),
                consumer_timeout_ms=self.timeout_ms,
                session_timeout_ms=self.config.get("session_timeout_ms", 45000),
                max_poll_records=self.config.get("max_poll_records", 10)
            )
            self._connected = True
            logger.info(f"Connected to Kafka at {self.bootstrap_servers}")
            logger.info(f"Subscribed to topics: {self.topics}")
            return True
        except Exception as e:
            logger.error(f"Failed to connect to Kafka: {e}")
            return False
    
    def consume(self) -> Iterator[Dict[str, Any]]:
        """
        Consume messages from Kafka.
        
        Yields messages until timeout (no more messages available).
        
        Yields:
            Dict containing job offer data
        """
        if not self._connect():
            # If Kafka not available, try to read from local mock file
            yield from self._consume_mock_data()
            return
        
        message_count = 0
        try:
            for message in self.consumer:
                message_count += 1
                logger.debug(f"Received message {message_count} from {message.topic}")
                
                # Add metadata to message
                data = message.value
                data["_kafka_metadata"] = {
                    "topic": message.topic,
                    "partition": message.partition,
                    "offset": message.offset,
                    "timestamp": message.timestamp
                }
                
                yield data
                
        except StopIteration:
            logger.info(f"Consumer timeout - no more messages. Total: {message_count}")
        except Exception as e:
            logger.error(f"Error consuming messages: {e}")
        
        logger.info(f"Finished consuming. Total messages: {message_count}")
    
    def _consume_mock_data(self) -> Iterator[Dict[str, Any]]:
        """
        Consume from mock data file for testing/development.
        
        Reads from data/mock_jobs.json if it exists.
        """
        from pathlib import Path
        
        mock_file = Path("data/mock_jobs.json")
        if not mock_file.exists():
            logger.warning("No Kafka connection and no mock data file found")
            return
        
        logger.info("Using mock data file for development")
        
        try:
            with open(mock_file, "r") as f:
                mock_jobs = json.load(f)
            
            if isinstance(mock_jobs, list):
                for job in mock_jobs:
                    yield job
            else:
                yield mock_jobs
        except Exception as e:
            logger.error(f"Failed to read mock data: {e}")
    
    def close(self):
        """Close the Kafka consumer connection."""
        if self.consumer:
            try:
                self.consumer.close()
                logger.info("Kafka consumer closed")
            except Exception as e:
                logger.error(f"Error closing consumer: {e}")
            finally:
                self._connected = False
    
    def get_topic_partitions(self) -> Dict[str, List[int]]:
        """Get partitions for subscribed topics."""
        if not self._connected:
            return {}
        
        result = {}
        for topic in self.topics:
            partitions = self.consumer.partitions_for_topic(topic)
            if partitions:
                result[topic] = list(partitions)
        
        return result
