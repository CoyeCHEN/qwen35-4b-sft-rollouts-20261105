FROM python:3.12-slim

WORKDIR /workspace
COPY official_reward.py /tests/official_reward.py
COPY record.json /tests/record.json
COPY test.sh /tests/test.sh
COPY evaluate.py /tests/evaluate.py
COPY rubric_verifier.py /tests/rubric_verifier.py
RUN chmod +x /tests/test.sh

CMD ["sleep", "infinity"]
