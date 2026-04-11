#!/usr/bin/env node
import "source-map-support/register";
import * as cdk from "aws-cdk-lib";
import { CodeLensStack } from "../lib/codelens-stack";

const app = new cdk.App();
const environment = (process.env.ENVIRONMENT ?? "dev") as "dev" | "staging" | "prod";

new CodeLensStack(app, `CodeLens-${environment}`, {
  environment,
  env: {
    account: process.env.CDK_DEFAULT_ACCOUNT,
    region:  process.env.CDK_DEFAULT_REGION ?? "eu-west-2",
  },
  description: "CodeLens — LLM-powered codebase analysis platform",
});

app.synth();
