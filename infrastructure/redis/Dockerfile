FROM redis@sha256:1db42ccef14898aa29bae778452d567534b59c107129cbc1163fb552de184d3c

USER redis

HEALTHCHECK --interval=10s --timeout=5s --start-period=10s --retries=5 \
    CMD ["sh", "-c", "REDISCLI_AUTH=\"$REDIS_PASSWORD\" redis-cli ping"]
