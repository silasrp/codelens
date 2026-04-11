.PHONY: infra-up infra-reset infra-status test api

infra-up:
	docker compose up localstack qdrant -d
	@echo "Waiting for LocalStack to be ready..."
	@sleep 12
	awslocal sqs create-queue \
		--queue-name codelens-analysis-dev \
		--region eu-west-2 \
		--attributes VisibilityTimeout=900
	awslocal dynamodb create-table \
		--table-name codelens-jobs-dev \
		--attribute-definitions AttributeName=job_id,AttributeType=S \
		--key-schema AttributeName=job_id,KeyType=HASH \
		--billing-mode PAY_PER_REQUEST \
		--region eu-west-2
	awslocal s3 mb s3://codelens-storage-dev --region eu-west-2
	@echo ""
	@echo "==> All resources ready"
	@$(MAKE) infra-status

infra-reset:
	docker compose down -v
	$(MAKE) infra-up

infra-status:
	@echo "--- SQS ---"
	@awslocal sqs get-queue-url --queue-name codelens-analysis-dev --region eu-west-2 2>/dev/null && echo "  OK" || echo "  MISSING"
	@echo "--- DynamoDB ---"
	@awslocal dynamodb describe-table --table-name codelens-jobs-dev --region eu-west-2 \
		--query 'Table.{Key:KeySchema[0].AttributeName,Status:TableStatus}' 2>/dev/null || echo "  MISSING"
	@echo "--- S3 ---"
	@awslocal s3 ls s3://codelens-storage-dev 2>/dev/null && echo "  OK" || echo "  MISSING"

test:
	cd services/api && pytest tests/ -v

api:
	cd services/api && uvicorn main:app --reload --port 8000
