FROM public.ecr.aws/lambda/python:3.12

WORKDIR ${LAMBDA_TASK_ROOT}

RUN dnf install -y gcc git && dnf clean all

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
COPY ../api/core ./core

CMD ["handler.handler"]
