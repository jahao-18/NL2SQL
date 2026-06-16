# Elasticsearch 8.13 + IK 中文分词插件(analysis-ik)。
# 烤进镜像而非容器内手装,保证 docker compose up -d --build 后插件常在、可重建。
# 插件大版本必须与 ES 完全一致(8.13.0),否则装不上。
FROM docker.elastic.co/elasticsearch/elasticsearch:8.13.0

# --batch 自动接受插件权限提示;URL 用 infinilabs 官方发布源(medcl/IK 的现维护方)。
RUN bin/elasticsearch-plugin install --batch \
    https://get.infini.cloud/elasticsearch/analysis-ik/8.13.0
