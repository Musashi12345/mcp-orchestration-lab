FROM python:3.12-slim@sha256:a0f57064cbdcd6285fa45f51237ab0b35ea8ebaed06a1f5973e89e19dfb86704
ARG SDK_SHA256
LABEL lab.csv_python_sdk_sha256=$SDK_SHA256
COPY src/mcp_execution_lab/program_sdk /opt/runner/program_sdk
USER 65532:65532
WORKDIR /tmp
ENTRYPOINT ["python", "-I", "-u", "/opt/runner/program_sdk/entrypoint.py"]
