ARG PYTHON_IMAGE=python:3.12-slim-bookworm

FROM ${PYTHON_IMAGE} AS builder

ARG UV_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple
ENV UV_INDEX_URL=${UV_INDEX_URL}

RUN pip install --no-cache-dir uv -i ${UV_INDEX_URL}

WORKDIR /app
COPY pyproject.toml README.md ./
COPY fast_odoo_mcp/ fast_odoo_mcp/
RUN uv pip install --system .

FROM ${PYTHON_IMAGE}

RUN useradd -m -u 1000 mcp

COPY --from=builder --chown=mcp:mcp /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder --chown=mcp:mcp /usr/local/bin/fast-odoo-mcp /usr/local/bin/

ENV PYTHONUNBUFFERED=1

RUN echo "mcp soft nofile 65536" >> /etc/security/limits.conf &&     echo "mcp hard nofile 65536" >> /etc/security/limits.conf

LABEL org.opencontainers.image.title="fast-odoo-mcp"
LABEL org.opencontainers.image.description="MCP Server for Odoo ERP — connect AI assistants to Odoo via JSON/2 & XML-RPC"
LABEL org.opencontainers.image.url="https://github.com/hjdhnx/fast-odoo-mcp"
LABEL org.opencontainers.image.source="https://github.com/hjdhnx/fast-odoo-mcp"
LABEL org.opencontainers.image.licenses="MPL-2.0"

USER mcp

ENTRYPOINT ["fast-odoo-mcp"]
