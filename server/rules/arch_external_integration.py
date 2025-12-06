"""KB-enriching rule: Detect external system integrations.

This rule identifies where the application connects to external systems:
- HTTP clients (requests, axios, fetch, HttpClient)
- Database connections (SQLAlchemy, Prisma, JDBC, Entity Framework)
- Message queues (Redis, RabbitMQ, Kafka, SQS)
- Third-party APIs and SDKs (Stripe, AWS, Twilio, etc.)
- File storage services (S3, GCS, Azure Blob)

PURPOSE: This is a KB-enriching rule. It does NOT flag problems - it provides
architectural intelligence that enriches the .aspect/structure.md file to help
AI coding agents understand what external dependencies the system has.

SEVERITY: "info" - These are not issues, they are structural annotations.
"""

from typing import Iterator, Dict, List, Set

try:
    from ..engine.types import Rule, Finding, RuleMeta, Requires, RuleContext
except ImportError:
    import sys
    import os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
    from engine.types import Rule, Finding, RuleMeta, Requires, RuleContext


class ArchExternalIntegrationRule:
    """Detect external system integrations for KB enrichment."""
    
    meta = RuleMeta(
        id="arch.external_integration",
        category="arch",
        tier=0,  # File-level analysis
        priority="P2",  # KB enrichment
        autofix_safety="suggest-only",
        description="Detect external system integrations (HTTP clients, databases, message queues, third-party APIs)",
        langs=["python", "typescript", "javascript", "java", "csharp", "go", "ruby", "rust"],
        surface="kb"  # KB-only: powers .aspect/ architecture knowledge, not shown to users
    )
    requires = Requires(syntax=True, raw_text=True)

    # HTTP client patterns by language
    HTTP_CLIENTS: Dict[str, Dict[str, str]] = {
        "python": {
            "requests.get": "HTTP Client (requests)",
            "requests.post": "HTTP Client (requests)",
            "requests.put": "HTTP Client (requests)",
            "requests.delete": "HTTP Client (requests)",
            "requests.request": "HTTP Client (requests)",
            "requests.Session": "HTTP Client (requests)",
            "httpx.get": "HTTP Client (httpx)",
            "httpx.post": "HTTP Client (httpx)",
            "httpx.AsyncClient": "HTTP Client (httpx async)",
            "aiohttp.ClientSession": "HTTP Client (aiohttp)",
            "urllib.request.urlopen": "HTTP Client (urllib)",
            "http.client.HTTPConnection": "HTTP Client (http.client)",
        },
        "javascript": {
            "fetch(": "HTTP Client (fetch)",
            "axios.get": "HTTP Client (axios)",
            "axios.post": "HTTP Client (axios)",
            "axios.create": "HTTP Client (axios)",
            "got(": "HTTP Client (got)",
            "superagent": "HTTP Client (superagent)",
            "node-fetch": "HTTP Client (node-fetch)",
            "XMLHttpRequest": "HTTP Client (XHR)",
        },
        "typescript": {
            "fetch(": "HTTP Client (fetch)",
            "axios.get": "HTTP Client (axios)",
            "axios.post": "HTTP Client (axios)",
            "axios.create": "HTTP Client (axios)",
            "got(": "HTTP Client (got)",
            "HttpClient": "HTTP Client (Angular)",
        },
        "java": {
            "HttpClient": "HTTP Client (Java HttpClient)",
            "HttpURLConnection": "HTTP Client (HttpURLConnection)",
            "RestTemplate": "HTTP Client (Spring RestTemplate)",
            "WebClient": "HTTP Client (Spring WebClient)",
            "OkHttpClient": "HTTP Client (OkHttp)",
            "Retrofit": "HTTP Client (Retrofit)",
        },
        "csharp": {
            "HttpClient": "HTTP Client (HttpClient)",
            "WebClient": "HTTP Client (WebClient)",
            "HttpWebRequest": "HTTP Client (HttpWebRequest)",
            "RestClient": "HTTP Client (RestSharp)",
        },
        "go": {
            "http.Get": "HTTP Client (net/http)",
            "http.Post": "HTTP Client (net/http)",
            "http.NewRequest": "HTTP Client (net/http)",
            "http.Client": "HTTP Client (net/http)",
        },
        "ruby": {
            "Net::HTTP": "HTTP Client (Net::HTTP)",
            "Faraday": "HTTP Client (Faraday)",
            "HTTParty": "HTTP Client (HTTParty)",
            "RestClient": "HTTP Client (RestClient)",
        },
        "rust": {
            "reqwest::get": "HTTP Client (reqwest)",
            "reqwest::Client": "HTTP Client (reqwest)",
            "hyper::Client": "HTTP Client (hyper)",
        },
    }

    # Database connection patterns
    DATABASE_PATTERNS: Dict[str, Dict[str, str]] = {
        "python": {
            "create_engine": "Database (SQLAlchemy)",
            "sessionmaker": "Database (SQLAlchemy)",
            "AsyncSession": "Database (SQLAlchemy async)",
            "psycopg2.connect": "Database (PostgreSQL)",
            "psycopg.connect": "Database (PostgreSQL)",
            "asyncpg.connect": "Database (PostgreSQL async)",
            "pymysql.connect": "Database (MySQL)",
            "mysql.connector": "Database (MySQL)",
            "pymongo.MongoClient": "Database (MongoDB)",
            "motor.motor_asyncio": "Database (MongoDB async)",
            "redis.Redis": "Cache (Redis)",
            "aioredis": "Cache (Redis async)",
            "sqlite3.connect": "Database (SQLite)",
            "tortoise.Tortoise": "Database (Tortoise ORM)",
            "databases.Database": "Database (encode/databases)",
        },
        "javascript": {
            "mongoose.connect": "Database (MongoDB/Mongoose)",
            "MongoClient": "Database (MongoDB)",
            "createConnection": "Database (TypeORM/Sequelize)",
            "PrismaClient": "Database (Prisma)",
            "knex(": "Database (Knex.js)",
            "pg.Pool": "Database (PostgreSQL)",
            "mysql.createConnection": "Database (MySQL)",
            "redis.createClient": "Cache (Redis)",
            "ioredis": "Cache (Redis)",
        },
        "typescript": {
            "mongoose.connect": "Database (MongoDB/Mongoose)",
            "MongoClient": "Database (MongoDB)",
            "DataSource": "Database (TypeORM)",
            "PrismaClient": "Database (Prisma)",
            "createConnection": "Database (TypeORM)",
            "Sequelize": "Database (Sequelize)",
            "knex(": "Database (Knex.js)",
            "redis.createClient": "Cache (Redis)",
        },
        "java": {
            "DriverManager.getConnection": "Database (JDBC)",
            "DataSource": "Database (DataSource)",
            "EntityManager": "Database (JPA)",
            "JdbcTemplate": "Database (Spring JDBC)",
            "MongoClient": "Database (MongoDB)",
            "Jedis": "Cache (Redis)",
            "RedisTemplate": "Cache (Redis/Spring)",
        },
        "csharp": {
            "SqlConnection": "Database (SQL Server)",
            "NpgsqlConnection": "Database (PostgreSQL)",
            "MySqlConnection": "Database (MySQL)",
            "DbContext": "Database (Entity Framework)",
            "MongoClient": "Database (MongoDB)",
            "ConnectionMultiplexer": "Cache (Redis)",
            "IDatabase": "Cache (Redis)",
        },
        "go": {
            "sql.Open": "Database (database/sql)",
            "gorm.Open": "Database (GORM)",
            "pgx.Connect": "Database (PostgreSQL)",
            "mongo.Connect": "Database (MongoDB)",
            "redis.NewClient": "Cache (Redis)",
        },
        "ruby": {
            "ActiveRecord::Base": "Database (ActiveRecord)",
            "Sequel.connect": "Database (Sequel)",
            "PG.connect": "Database (PostgreSQL)",
            "Mysql2::Client": "Database (MySQL)",
            "Mongo::Client": "Database (MongoDB)",
            "Redis.new": "Cache (Redis)",
        },
        "rust": {
            "sqlx::PgPool": "Database (PostgreSQL/sqlx)",
            "diesel::PgConnection": "Database (PostgreSQL/Diesel)",
            "mongodb::Client": "Database (MongoDB)",
            "redis::Client": "Cache (Redis)",
        },
    }

    # Message queue patterns
    MESSAGE_QUEUE_PATTERNS: Dict[str, Dict[str, str]] = {
        "python": {
            "pika.BlockingConnection": "Message Queue (RabbitMQ)",
            "aio_pika": "Message Queue (RabbitMQ async)",
            "kombu": "Message Queue (Kombu/Celery)",
            "celery.Celery": "Message Queue (Celery)",
            "kafka.KafkaProducer": "Message Queue (Kafka)",
            "kafka.KafkaConsumer": "Message Queue (Kafka)",
            "aiokafka": "Message Queue (Kafka async)",
            "boto3.client('sqs')": "Message Queue (AWS SQS)",
            "boto3.resource('sqs')": "Message Queue (AWS SQS)",
            "google.cloud.pubsub": "Message Queue (GCP Pub/Sub)",
        },
        "javascript": {
            "amqplib": "Message Queue (RabbitMQ)",
            "kafkajs": "Message Queue (Kafka)",
            "bull": "Message Queue (Bull/Redis)",
            "bullmq": "Message Queue (BullMQ/Redis)",
            "SQSClient": "Message Queue (AWS SQS)",
            "@google-cloud/pubsub": "Message Queue (GCP Pub/Sub)",
        },
        "typescript": {
            "amqplib": "Message Queue (RabbitMQ)",
            "kafkajs": "Message Queue (Kafka)",
            "bull": "Message Queue (Bull/Redis)",
            "bullmq": "Message Queue (BullMQ/Redis)",
            "SQSClient": "Message Queue (AWS SQS)",
        },
        "java": {
            "RabbitTemplate": "Message Queue (RabbitMQ/Spring)",
            "KafkaTemplate": "Message Queue (Kafka/Spring)",
            "JmsTemplate": "Message Queue (JMS)",
            "AmazonSQS": "Message Queue (AWS SQS)",
            "ConnectionFactory": "Message Queue (JMS)",
        },
        "csharp": {
            "RabbitMQ.Client": "Message Queue (RabbitMQ)",
            "Confluent.Kafka": "Message Queue (Kafka)",
            "AmazonSQSClient": "Message Queue (AWS SQS)",
            "ServiceBusClient": "Message Queue (Azure Service Bus)",
        },
        "go": {
            "amqp.Dial": "Message Queue (RabbitMQ)",
            "sarama": "Message Queue (Kafka)",
            "sqs.New": "Message Queue (AWS SQS)",
        },
        "ruby": {
            "Bunny.new": "Message Queue (RabbitMQ)",
            "ruby-kafka": "Message Queue (Kafka)",
            "Aws::SQS": "Message Queue (AWS SQS)",
        },
        "rust": {
            "lapin": "Message Queue (RabbitMQ)",
            "rdkafka": "Message Queue (Kafka)",
            "rusoto_sqs": "Message Queue (AWS SQS)",
        },
    }

    # Cloud/Third-party SDK patterns
    THIRD_PARTY_SDKS: Dict[str, Dict[str, str]] = {
        "python": {
            "boto3": "Cloud (AWS SDK)",
            "google.cloud": "Cloud (GCP SDK)",
            "azure.": "Cloud (Azure SDK)",
            "stripe.": "Payment (Stripe)",
            "twilio.": "Communication (Twilio)",
            "sendgrid.": "Email (SendGrid)",
            "slack_sdk": "Communication (Slack)",
            "openai.": "AI (OpenAI)",
            "anthropic.": "AI (Anthropic)",
        },
        "javascript": {
            "@aws-sdk/": "Cloud (AWS SDK)",
            "aws-sdk": "Cloud (AWS SDK)",
            "@google-cloud/": "Cloud (GCP SDK)",
            "@azure/": "Cloud (Azure SDK)",
            "stripe": "Payment (Stripe)",
            "twilio": "Communication (Twilio)",
            "@sendgrid/": "Email (SendGrid)",
            "@slack/": "Communication (Slack)",
            "openai": "AI (OpenAI)",
        },
        "typescript": {
            "@aws-sdk/": "Cloud (AWS SDK)",
            "aws-sdk": "Cloud (AWS SDK)",
            "@google-cloud/": "Cloud (GCP SDK)",
            "@azure/": "Cloud (Azure SDK)",
            "stripe": "Payment (Stripe)",
            "twilio": "Communication (Twilio)",
            "@sendgrid/": "Email (SendGrid)",
            "openai": "AI (OpenAI)",
        },
        "java": {
            "com.amazonaws": "Cloud (AWS SDK)",
            "com.google.cloud": "Cloud (GCP SDK)",
            "com.azure": "Cloud (Azure SDK)",
            "com.stripe": "Payment (Stripe)",
            "com.twilio": "Communication (Twilio)",
        },
        "csharp": {
            "Amazon.": "Cloud (AWS SDK)",
            "Google.Cloud": "Cloud (GCP SDK)",
            "Azure.": "Cloud (Azure SDK)",
            "Stripe": "Payment (Stripe)",
            "Twilio": "Communication (Twilio)",
        },
        "go": {
            "github.com/aws/aws-sdk-go": "Cloud (AWS SDK)",
            "cloud.google.com/go": "Cloud (GCP SDK)",
            "github.com/Azure/azure-sdk-for-go": "Cloud (Azure SDK)",
            "github.com/stripe/stripe-go": "Payment (Stripe)",
        },
        "ruby": {
            "aws-sdk": "Cloud (AWS SDK)",
            "google-cloud": "Cloud (GCP SDK)",
            "azure": "Cloud (Azure SDK)",
            "stripe": "Payment (Stripe)",
            "twilio-ruby": "Communication (Twilio)",
        },
        "rust": {
            "aws-sdk-": "Cloud (AWS SDK)",
            "google-cloud": "Cloud (GCP SDK)",
            "azure_": "Cloud (Azure SDK)",
        },
    }

    # File storage patterns
    FILE_STORAGE_PATTERNS: Dict[str, Dict[str, str]] = {
        "python": {
            "boto3.client('s3')": "Storage (AWS S3)",
            "boto3.resource('s3')": "Storage (AWS S3)",
            "google.cloud.storage": "Storage (GCP Cloud Storage)",
            "azure.storage.blob": "Storage (Azure Blob)",
            "minio.Minio": "Storage (MinIO/S3-compatible)",
        },
        "javascript": {
            "S3Client": "Storage (AWS S3)",
            "@google-cloud/storage": "Storage (GCP Cloud Storage)",
            "@azure/storage-blob": "Storage (Azure Blob)",
        },
        "typescript": {
            "S3Client": "Storage (AWS S3)",
            "@google-cloud/storage": "Storage (GCP Cloud Storage)",
            "@azure/storage-blob": "Storage (Azure Blob)",
        },
        "java": {
            "AmazonS3": "Storage (AWS S3)",
            "S3Client": "Storage (AWS S3)",
            "Storage": "Storage (GCP Cloud Storage)",
            "BlobServiceClient": "Storage (Azure Blob)",
        },
        "csharp": {
            "AmazonS3Client": "Storage (AWS S3)",
            "StorageClient": "Storage (GCP Cloud Storage)",
            "BlobServiceClient": "Storage (Azure Blob)",
        },
        "go": {
            "s3.New": "Storage (AWS S3)",
            "storage.NewClient": "Storage (GCP Cloud Storage)",
            "azblob.": "Storage (Azure Blob)",
        },
        "ruby": {
            "Aws::S3::Client": "Storage (AWS S3)",
            "Google::Cloud::Storage": "Storage (GCP Cloud Storage)",
            "Azure::Storage::Blob": "Storage (Azure Blob)",
        },
        "rust": {
            "aws_sdk_s3": "Storage (AWS S3)",
            "cloud-storage": "Storage (GCP Cloud Storage)",
        },
    }

    def visit(self, ctx: RuleContext) -> Iterator[Finding]:
        """Detect external integrations and emit info-level findings."""
        if not ctx.syntax:
            return

        lang = ctx.language
        text = ctx.text
        
        # Combine all patterns for this language
        all_patterns: Dict[str, str] = {}
        for pattern_dict in [
            self.HTTP_CLIENTS,
            self.DATABASE_PATTERNS,
            self.MESSAGE_QUEUE_PATTERNS,
            self.THIRD_PARTY_SDKS,
            self.FILE_STORAGE_PATTERNS,
        ]:
            if lang in pattern_dict:
                all_patterns.update(pattern_dict[lang])

        if not all_patterns:
            return

        # Track found integrations to avoid duplicates
        found_integrations: Set[str] = set()
        
        # Search for patterns in the text
        for pattern, integration_type in all_patterns.items():
            if pattern in text:
                # Find all occurrences
                idx = 0
                while True:
                    idx = text.find(pattern, idx)
                    if idx == -1:
                        break
                    
                    # Create a unique key for this integration
                    integration_key = f"{integration_type}:{idx}"
                    if integration_key not in found_integrations:
                        found_integrations.add(integration_key)
                        
                        # Find line number for context
                        line_start = text.rfind('\n', 0, idx) + 1
                        line_end = text.find('\n', idx)
                        if line_end == -1:
                            line_end = len(text)
                        
                        yield Finding(
                            rule=self.meta.id,
                            message=f"External integration: {integration_type}",
                            file=ctx.file_path,
                            start_byte=idx,
                            end_byte=idx + len(pattern),
                            severity="info",
                            meta={
                                'integration_type': integration_type,
                                'pattern': pattern,
                                'category': self._categorize_integration(integration_type),
                            }
                        )
                    
                    idx += 1

    def _categorize_integration(self, integration_type: str) -> str:
        """Categorize integration into high-level type."""
        if "HTTP Client" in integration_type:
            return "http_client"
        elif "Database" in integration_type:
            return "database"
        elif "Cache" in integration_type:
            return "cache"
        elif "Message Queue" in integration_type:
            return "message_queue"
        elif "Cloud" in integration_type:
            return "cloud"
        elif "Storage" in integration_type:
            return "storage"
        elif "Payment" in integration_type:
            return "payment"
        elif "Communication" in integration_type:
            return "communication"
        elif "AI" in integration_type:
            return "ai"
        elif "Email" in integration_type:
            return "email"
        else:
            return "other"


# Module-level instance for rule registration
rule = ArchExternalIntegrationRule()

