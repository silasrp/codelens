import * as cdk from "aws-cdk-lib";
import * as dynamodb from "aws-cdk-lib/aws-dynamodb";
import * as ecr_assets from "aws-cdk-lib/aws-ecr-assets";
import * as iam from "aws-cdk-lib/aws-iam";
import * as lambda from "aws-cdk-lib/aws-lambda";
import * as lambdaEventSources from "aws-cdk-lib/aws-lambda-event-sources";
import * as s3 from "aws-cdk-lib/aws-s3";
import * as ssm from "aws-cdk-lib/aws-ssm";
import * as sqs from "aws-cdk-lib/aws-sqs";
import { Construct } from "constructs";

export interface CodeLensStackProps extends cdk.StackProps {
  environment: "dev" | "staging" | "prod";
}

export class CodeLensStack extends cdk.Stack {
  public readonly jobsTable:      dynamodb.Table;
  public readonly analysisQueue:  sqs.Queue;
  public readonly storageBucket:  s3.Bucket;
  public readonly orchestratorFn: lambda.DockerImageFunction;

  constructor(scope: Construct, id: string, props: CodeLensStackProps) {
    super(scope, id, props);

    const isProd = props.environment === "prod";
    const env    = props.environment;

    // ── SSM secrets (stored before deploy — never appear in CDK output) ──
    // Pass parameter paths — the Lambda resolves them at cold start via SSM API.
    const qdrantUrl  = ssm.StringParameter.valueForStringParameter(this, "/codelens/qdrant-url");

    // ── S3 ───────────────────────────────────────────────────────────────
    this.storageBucket = new s3.Bucket(this, "Storage", {
      bucketName:          `codelens-storage-${env}-${this.account}`,
      versioned:           isProd,
      removalPolicy:       isProd ? cdk.RemovalPolicy.RETAIN : cdk.RemovalPolicy.DESTROY,
      autoDeleteObjects:   !isProd,
      blockPublicAccess:   s3.BlockPublicAccess.BLOCK_ALL,
      encryption:          s3.BucketEncryption.S3_MANAGED,
      lifecycleRules:      [{ prefix: "source/", expiration: cdk.Duration.days(7) }],
    });

    // ── DynamoDB ─────────────────────────────────────────────────────────
    this.jobsTable = new dynamodb.Table(this, "Jobs", {
      tableName:            `codelens-jobs-${env}`,
      partitionKey:         { name: "job_id", type: dynamodb.AttributeType.STRING },
      billingMode:          dynamodb.BillingMode.PAY_PER_REQUEST,
      removalPolicy:        isProd ? cdk.RemovalPolicy.RETAIN : cdk.RemovalPolicy.DESTROY,
      timeToLiveAttribute:  "expires_at",
      pointInTimeRecoverySpecification: isProd ? { pointInTimeRecoveryEnabled: true } : undefined,
    });

    this.jobsTable.addGlobalSecondaryIndex({
      indexName:      "status-created-index",
      partitionKey:   { name: "status",     type: dynamodb.AttributeType.STRING },
      sortKey:        { name: "created_at", type: dynamodb.AttributeType.STRING },
      projectionType: dynamodb.ProjectionType.ALL,
    });

    // ── SQS + DLQ ────────────────────────────────────────────────────────
    const dlq = new sqs.Queue(this, "DLQ", {
      queueName:       `codelens-analysis-dlq-${env}`,
      retentionPeriod: cdk.Duration.days(14),
    });

    this.analysisQueue = new sqs.Queue(this, "Queue", {
      queueName:         `codelens-analysis-${env}`,
      visibilityTimeout: cdk.Duration.minutes(15),
      deadLetterQueue:   { queue: dlq, maxReceiveCount: 3 },
    });

    // ── Lambda (Docker — tree-sitter needs compiled C extensions) ────────
    this.orchestratorFn = new lambda.DockerImageFunction(this, "Orchestrator", {
      functionName: `codelens-orchestrator-${env}`,
      code: lambda.DockerImageCode.fromImageAsset("../services", {
        file: "lambda/Dockerfile",
        platform: ecr_assets.Platform.LINUX_AMD64,
      }),
      memorySize: 2048,
      timeout:    cdk.Duration.minutes(14),
      environment: {
        DYNAMODB_TABLE:  this.jobsTable.tableName,
        S3_BUCKET:       this.storageBucket.bucketName,
        AWS_ACCOUNT:     this.account,
        SSM_OPENAI_API_KEY:  "/codelens/openai-api-key",
        SSM_VOYAGE_API_KEY:  "/codelens/voyage-api-key",
        QDRANT_URL:          qdrantUrl,
        SSM_QDRANT_API_KEY:  "/codelens/qdrant-api-key",
      },
    });

    this.orchestratorFn.addEventSource(
      new lambdaEventSources.SqsEventSource(this.analysisQueue, {
        batchSize: 1,
        reportBatchItemFailures: true,
      })
    );

    this.storageBucket.grantReadWrite(this.orchestratorFn);
    this.jobsTable.grantReadWriteData(this.orchestratorFn);

    // Lambda needs to read SSM params at cold start
    this.orchestratorFn.addToRolePolicy(new iam.PolicyStatement({
      actions:   ["ssm:GetParameter", "ssm:GetParameters"],
      resources: [`arn:aws:ssm:${this.region}:${this.account}:parameter/codelens/*`],
    }));

    // ── Outputs ───────────────────────────────────────────────────────────
    new cdk.CfnOutput(this, "QueueUrl",   { value: this.analysisQueue.queueUrl,       exportName: `codelens-queue-url-${env}`   });
    new cdk.CfnOutput(this, "BucketName", { value: this.storageBucket.bucketName,     exportName: `codelens-bucket-${env}`      });
    new cdk.CfnOutput(this, "TableName",  { value: this.jobsTable.tableName,          exportName: `codelens-table-${env}`       });
    new cdk.CfnOutput(this, "FunctionArn",{ value: this.orchestratorFn.functionArn });

    cdk.Tags.of(this).add("Project",     "codelens");
    cdk.Tags.of(this).add("Environment", env);
  }
}
