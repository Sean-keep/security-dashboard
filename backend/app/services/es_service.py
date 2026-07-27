"""
Elasticsearch Service - Async + Health Check + Error Transparency
"""
import re
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
from elasticsearch import Elasticsearch, NotFoundError, ConnectionError, AuthenticationException
from pydantic import BaseModel


logger = logging.getLogger(__name__)


class ESConfig(BaseModel):
    """ES connection configuration"""
    host: str = "localhost"
    port: int = 9200
    scheme: str = "https"
    user: str = ""
    password: str = ""
    verify_certs: bool = False
    default_index: str = "security-logs-*"


class ESHealthStatus(BaseModel):
    """ES health check result"""
    connected: bool
    authenticated: bool
    latency_ms: Optional[float] = None
    cluster_name: Optional[str] = None
    version: Optional[str] = None
    error: Optional[str] = None


class ESService:
    """
    Elasticsearch Service

    Features:
    - Support HTTPS and SSL certificate verification control
    - Health check with detailed status
    - Multi-stage rule execution
    - Error transparency (no silent swallowing)
    """

    def __init__(self, config: ESConfig = None, **kwargs):
        """Initialize ES service with configuration"""
        self.config = config or ESConfig(**kwargs)
        self._client: Optional[Elasticsearch] = None
        self._field_type_cache: Dict[str, str] = {}

    @property
    def client(self) -> Elasticsearch:
        """Get or create ES client"""
        if self._client is None:
            url = f"{self.config.scheme}://{self.config.host}:{self.config.port}"

            kwargs = {}

            # SSL settings
            if not self.config.verify_certs:
                kwargs["verify_certs"] = False
            else:
                kwargs["verify_certs"] = True

            # Auth
            if self.config.user and self.config.password:
                kwargs["basic_auth"] = (self.config.user, self.config.password)

            try:
                self._client = Elasticsearch(
                    [url],
                    **kwargs
                )
            except Exception as e:
                logger.error(f"Failed to create ES client: {e}")
                raise

        return self._client

    def check_health(self) -> ESHealthStatus:
        """
        Check ES connection health

        Returns detailed status including:
        - Connection status
        - Authentication status
        - Latency
        - Cluster info
        - Error message if failed
        """
        import time

        try:
            start = time.time()
            info = self.client.info()
            latency = (time.time() - start) * 1000

            return ESHealthStatus(
                connected=True,
                authenticated=True,
                latency_ms=round(latency, 2),
                cluster_name=info.get("cluster_name"),
                version=info.get("version", {}).get("number"),
            )
        except AuthenticationException as e:
            return ESHealthStatus(
                connected=True,
                authenticated=False,
                error=f"Authentication failed: {str(e)}"
            )
        except ConnectionError as e:
            return ESHealthStatus(
                connected=False,
                authenticated=False,
                error=f"Connection failed: {str(e)}"
            )
        except Exception as e:
            return ESHealthStatus(
                connected=False,
                authenticated=False,
                error=f"Unexpected error: {str(e)}"
            )

    def list_indices(self, pattern: str = "*") -> List[Dict[str, Any]]:
        """
        List indices matching pattern

        Args:
            pattern: Index pattern to match

        Returns:
            List of {name, docs, size} dicts

        Raises:
            RuntimeError: If ES query fails
        """
        try:
            result = self.client.cat.indices(format="json", h="index,docs.count,store.size")

            indices = []
            for r in result:
                name = r.get("index", "")
                if pattern == "*" or re.match(pattern.replace("*", ".*"), name):
                    indices.append({
                        "name": name,
                        "docs": r.get("docs.count", "0"),
                        "size": r.get("store.size", "0b")
                    })

            return sorted(indices, key=lambda x: x["name"])

        except Exception as e:
            logger.error(f"Failed to list indices: {e}")
            raise RuntimeError(f"ES query failed: {str(e)}")

    def get_index_fields(self, index_pattern: str = None) -> Dict[str, str]:
        """
        Get field types for an index pattern

        Args:
            index_pattern: Index pattern (default: configured default_index)

        Returns:
            Dict of {field_name: field_type}
        """
        index = index_pattern or self.config.default_index

        if index in self._field_type_cache:
            return self._field_type_cache[index]

        try:
            result = self.client.indices.get_mapping(index=index)

            mappings = {}
            for idx, info in result.items():
                props = info.get("mappings", {}).get("properties", {})
                self._extract_field_types(props, "", mappings)

            self._field_type_cache[index] = mappings
            return mappings

        except NotFoundError:
            logger.warning(f"Index pattern not found: {index}")
            return {}
        except Exception as e:
            logger.error(f"Failed to get index fields: {e}")
            raise RuntimeError(f"ES query failed: {str(e)}")

    def _extract_field_types(self, props: Dict, prefix: str, result: Dict):
        """Recursively extract field types from mapping"""
        for field, meta in props.items():
            full_name = f"{prefix}{field}" if prefix else field
            field_type = meta.get("type", "unknown")

            # Store main type
            result[full_name] = field_type

            # Check for .keyword sub-field
            if field_type == "text":
                keyword_field = meta.get("fields", {}).get("keyword", {})
                if keyword_field:
                    result[f"{full_name}.keyword"] = "keyword"

            # Recurse into nested/object fields
            if "properties" in meta:
                self._extract_field_types(meta["properties"], f"{full_name}.", result)

    def execute_query(
        self,
        index_pattern: str = None,
        filters: List[Dict] = None,
        time_window: Dict = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Execute a simple query

        Args:
            index_pattern: ES index pattern
            filters: List of filter nodes
            time_window: Time window dict (e.g., {"minutes": 3})
            limit: Max results

        Returns:
            List of documents
        """
        index = index_pattern or self.config.default_index

        must_clauses = []

        # Add time filter
        if time_window:
            must_clauses.extend(self._build_time_filter(time_window))

        # Add other filters
        if filters:
            for f in filters:
                clause = self._build_filter_clause(f)
                if clause:
                    must_clauses.append(clause)

        body = {
            "size": limit,
            "query": {
                "bool": {
                    "must": must_clauses if must_clauses else [{"match_all": {}}]
                }
            },
            "sort": [{"@timestamp": {"order": "desc"}}]
        }

        try:
            result = self.client.search(index=index, body=body)
            return [hit["_source"] for hit in result.get("hits", {}).get("hits", [])]
        except Exception as e:
            logger.error(f"ES query failed: {e}")
            raise RuntimeError(f"ES query failed: {str(e)}")

    def execute_aggregation(
        self,
        index_pattern: str,
        filters: List[Dict],
        time_window: Dict,
        aggregation: Dict,
        limit: int = 1000
    ) -> List[Dict[str, Any]]:
        """
        Execute an aggregation query

        Args:
            index_pattern: ES index pattern
            filters: List of filter nodes
            time_window: Time window dict
            aggregation: Aggregation config (group_by, metric, having, alias)
            limit: Max buckets

        Returns:
            List of aggregation results
        """
        index = index_pattern or self.config.default_index
        group_by = aggregation.get("group_by", [])
        metric = aggregation.get("metric", "count")
        having = aggregation.get("having")
        alias = aggregation.get("alias", "count")

        # Build query
        must_clauses = []
        if time_window:
            must_clauses.extend(self._build_time_filter(time_window))
        if filters:
            for f in filters:
                clause = self._build_filter_clause(f)
                if clause:
                    must_clauses.append(clause)

        # Get field types to handle text fields
        field_types = self.get_index_fields(index)

        def get_agg_field(name: str) -> str:
            """Get aggregation-safe field name (append .keyword for text fields)"""
            if field_types.get(name) == "text" and field_types.get(f"{name}.keyword"):
                return f"{name}.keyword"
            return name

        # Build aggregation
        if len(group_by) > 1:
            # Multi-field group: nested terms
            agg_body = self._build_nested_aggregation(
                [get_agg_field(f) for f in group_by],
                group_by,  # Keep original names for results
                metric,
                alias,
                limit
            )
        elif len(group_by) == 1:
            # Single field group
            agg_field = get_agg_field(group_by[0])
            agg_body = {
                "single_group": {
                    "terms": {"field": agg_field, "size": limit},
                    "aggs": {
                        alias: self._build_metric_agg(metric, agg_field)
                    }
                }
            }
        else:
            # No group: just count
            body = {
                "size": 0,
                "query": {"bool": {"must": must_clauses if must_clauses else [{"match_all": {}}]}}
            }
            try:
                result = self.client.search(index=index, body=body)
                total = result.get("hits", {}).get("total", {}).get("value", 0)
                return [{alias: total}]
            except Exception as e:
                raise RuntimeError(f"ES query failed: {str(e)}")

        body = {
            "size": 0,
            "query": {"bool": {"must": must_clauses if must_clauses else [{"match_all": {}}]}},
            "aggs": agg_body
        }

        try:
            result = self.client.search(index=index, body=body)
            return self._parse_aggregation_result(result, group_by, alias, having)
        except Exception as e:
            logger.error(f"ES aggregation failed: {e}")
            raise RuntimeError(f"ES aggregation failed: {str(e)}")

    def execute_multi_stage_rule(
        self,
        stages: List[Dict],
        output_mapping: Dict = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Execute multi-stage rule with aggregation and cross-index join

        Args:
            stages: List of stage configs
            output_mapping: Output field mapping
            limit: Max results per stage

        Returns:
            List of merged results
        """
        stage_results = {}

        for stage in stages:
            stage_id = stage.get("id", "default")
            index = stage.get("index", self.config.default_index)
            time_window = stage.get("time_window", {})
            filters = stage.get("filters", [])
            aggregation = stage.get("aggregation")
            join = stage.get("join")

            # Extract join values from prior stage
            join_values = None
            if join:
                from_stage = join.get("from_stage")
                remote_field = join.get("remote_field")
                if from_stage in stage_results:
                    join_values = list(set(
                        row.get(remote_field)
                        for row in stage_results[from_stage]
                        if row.get(remote_field)
                    ))

            # Build query
            must_clauses = []
            if time_window:
                must_clauses.extend(self._build_time_filter(time_window))
            if filters:
                for f in filters:
                    clause = self._build_filter_clause(f)
                    if clause:
                        must_clauses.append(clause)
            if join_values and join.get("local_field"):
                # Use .keyword suffix for text fields in terms query
                join_field = join["local_field"]
                field_types = self.get_index_fields(index)
                if field_types.get(join_field) == "text" and field_types.get(f"{join_field}.keyword"):
                    join_field = f"{join_field}.keyword"
                must_clauses.append({"terms": {join_field: join_values}})

            # Execute
            if aggregation:
                results = self._execute_stage_aggregation(
                    index, must_clauses, aggregation, join, stage_results, limit
                )
            else:
                # No aggregation: raw doc search
                # If stage has a join, use collapse on join field to deduplicate
                # (ensures every matched join key gets a unique doc, not just the last one)
                body = {
                    "size": limit,
                    "query": {"bool": {"must": must_clauses if must_clauses else [{"match_all": {}}]}}
                }
                if join and join.get("local_field"):
                    # Determine correct field name for collapse
                    # (text fields need .keyword suffix for collapse/doc_values)
                    collapse_field = join["local_field"]
                    field_types = self.get_index_fields(index)
                    if field_types.get(collapse_field) == "text" and field_types.get(f"{collapse_field}.keyword"):
                        collapse_field = f"{collapse_field}.keyword"
                    body["collapse"] = {"field": collapse_field}
                try:
                    result = self.client.search(index=index, body=body)
                    results = [hit["_source"] for hit in result.get("hits", {}).get("hits", [])]
                except Exception as e:
                    raise RuntimeError(f"Stage {stage_id} query failed: {str(e)}")

            stage_results[stage_id] = results

        # Merge results
        results = self._merge_stage_results(stage_results, stages, output_mapping or {})

        # Attach stage data per result for template rendering ({stage.field} syntax)
        # Build a lookup: for each merged result, attach relevant stage result rows
        for r in results:
            r["_stages"] = {}
            for stage in stages:
                sid = stage.get("id")
                if sid in stage_results:
                    r["_stages"][sid] = stage_results[sid]

        return results

    def _build_time_filter(self, time_window: Dict) -> List[Dict]:
        """Build time range filter"""
        if not time_window:
            return []

        now = datetime.utcnow()
        delta = timedelta(**time_window)
        gte_time = (now - delta).isoformat() + "Z"

        return [{"range": {"@timestamp": {"gte": gte_time}}}]

    def _build_filter_clause(self, f: Dict) -> Optional[Dict]:
        """Build a single filter clause"""
        field = f.get("field", "")
        if not field:
            return None

        operator = f.get("operator", "equals")
        value = f.get("value", "")
        value_from = f.get("value_from", "")
        value_to = f.get("value_to", "")

        # Sanitize field name
        safe_field = re.sub(r'[^\w.\-]', '', field)

        # Auto-append .keyword for text fields in term-level queries
        safe_field_keyword = self._is_text_field(safe_field) and (safe_field + ".keyword") or safe_field

        if operator == "equals":
            return {"term": {safe_field_keyword: value}}
        elif operator == "not_equals":
            return {"bool": {"must_not": [{"term": {safe_field_keyword: value}}]}}
        elif operator == "contains":
            return {"wildcard": {safe_field: f"*{value}*"}}
        elif operator == "not_contains":
            return {"bool": {"must_not": [{"wildcard": {safe_field: f"*{value}*"}}]}}
        elif operator == "starts_with":
            return {"prefix": {safe_field: value}}
        elif operator == "ends_with":
            return {"wildcard": {safe_field: f"*{value}"}}
        elif operator in ("gt", "gte", "lt", "lte"):
            try:
                num_val = float(value)
                return {"range": {safe_field: {operator: num_val}}}
            except (ValueError, TypeError):
                return {"range": {safe_field: {operator: value}}}
        elif operator == "range":
            clause = {"range": {safe_field: {}}}
            if value_from:
                clause["range"][safe_field]["gte"] = value_from
            if value_to:
                clause["range"][safe_field]["lte"] = value_to
            return clause if clause["range"][safe_field] else None
        elif operator == "exists":
            return {"exists": {"field": safe_field}}
        elif operator == "not_exists":
            return {"bool": {"must_not": [{"exists": {"field": safe_field}}]}}
        elif operator == "in":
            if isinstance(value, list):
                values = value
            elif isinstance(value, str):
                values = [v.strip() for v in value.split(",") if v.strip()]
            else:
                values = [value]
            return {"terms": {safe_field_keyword: values}}
        else:
            return {"term": {safe_field: value}}

    def _is_text_field(self, field_name: str) -> bool:
        """Check if a field is 'text' type (needs .keyword for term queries)"""
        if not field_name:
            return False
        try:
            fields = self.get_index_fields(self.config.default_index)
            if fields.get(field_name) == "text" and fields.get(f"{field_name}.keyword"):
                return True
        except Exception:
            pass
        return False

    def _build_nested_aggregation(
        self,
        agg_fields: List[str],
        result_fields: List[str],
        metric: str,
        alias: str,
        limit: int
    ) -> Dict:
        """Build nested terms aggregation for multi-field grouping"""
        agg = {}

        for i in range(len(agg_fields) - 1, -1, -1):
            field = agg_fields[i]
            if i == len(agg_fields) - 1:
                agg = {
                    field: {
                        "terms": {"field": field, "size": limit},
                        "aggs": {
                            alias: self._build_metric_agg(metric, field)
                        }
                    }
                }
            else:
                agg = {
                    field: {
                        "terms": {"field": field, "size": limit},
                        "aggs": agg
                    }
                }

        return agg

    def _build_metric_agg(self, metric: str, field: str) -> Dict:
        """Build metric aggregation"""
        if metric == "count":
            return {"value_count": {"field": field}}
        else:
            return {metric: {"field": field}}

    def _execute_stage_aggregation(
        self,
        index: str,
        must_clauses: List[Dict],
        aggregation: Dict,
        join: Optional[Dict],
        stage_results: Dict,
        limit: int
    ) -> List[Dict]:
        """Execute aggregation for a stage"""
        group_by = aggregation.get("group_by", [])
        metric = aggregation.get("metric", "count")
        having = aggregation.get("having")
        alias = aggregation.get("alias", "count")

        # Get field types
        field_types = self.get_index_fields(index)

        def get_agg_field(name: str) -> str:
            if field_types.get(name) == "text" and field_types.get(f"{name}.keyword"):
                return f"{name}.keyword"
            return name

        # Build aggregation
        if len(group_by) > 1:
            agg_body = self._build_nested_aggregation(
                [get_agg_field(f) for f in group_by],
                group_by,
                metric,
                alias,
                limit
            )
            # Add time stats for nested aggregation (at top level)
            agg_body["_time_stats"] = {"stats": {"field": "@timestamp"}}
        elif len(group_by) == 1:
            agg_field = get_agg_field(group_by[0])
            agg_body = {
                "single_group": {
                    "terms": {"field": agg_field, "size": limit},
                    "aggs": {alias: self._build_metric_agg(metric, agg_field)}
                }
            }
            # Inject time stats (min/max on @timestamp) so each result row gets start_time/end_time/duration
            agg_body["_time_stats"] = {"stats": {"field": "@timestamp"}}
        else:
            # No grouping - still include time stats
            agg_body = {"_time_stats": {"stats": {"field": "@timestamp"}}}
            body = {
                "size": 0,
                "query": {"bool": {"must": must_clauses if must_clauses else [{"match_all": {}}]}},
                "aggs": agg_body
            }
            try:
                result = self.client.search(index=index, body=body)
                total = result.get("hits", {}).get("total", {}).get("value", 0)
                ts = result.get("aggregations", {}).get("_time_stats", {})
                start_time = ts.get("min")
                end_time = ts.get("max")
                # ES @timestamp is in milliseconds; store duration in seconds
                duration_sec = round((end_time - start_time) / 1000, 2) if start_time and end_time else 0
                row = {alias: total}
                if start_time:
                    row["start_time"] = start_time
                    row["end_time"] = end_time
                    row["duration"] = duration_sec
                return [row]
            except Exception as e:
                raise RuntimeError(f"ES query failed: {str(e)}")

        body = {
            "size": 0,
            "query": {"bool": {"must": must_clauses if must_clauses else [{"match_all": {}}]}},
            "aggs": agg_body
        }

        try:
            result = self.client.search(index=index, body=body)
            return self._parse_aggregation_result(result, group_by, alias, having)
        except Exception as e:
            raise RuntimeError(f"ES aggregation failed: {str(e)}")

    def _parse_aggregation_result(
        self,
        result: Dict,
        group_by: List[str],
        alias: str,
        having: Optional[Dict]
    ) -> List[Dict]:
        """Parse aggregation results"""
        results = []

        # Extract time stats (min/max of @timestamp) once
        ts_stats = result.get("aggregations", {}).get("_time_stats", {})
        ts_min = ts_stats.get("min")
        ts_max = ts_stats.get("max")
        # ES @timestamp is in milliseconds; store duration in seconds
        ts_duration = round((ts_max - ts_min) / 1000, 2) if (ts_min and ts_max) else None

        if len(group_by) > 1:
            # Nested aggregation
            def parse_nested(aggs: Dict, depth: int, row: Dict):
                if depth >= len(group_by):
                    row[alias] = aggs.get(alias, {}).get("value", 0)
                    if having and not self._check_having(row[alias], having):
                        return
                    results.append(row.copy())
                    return

                field = group_by[depth]
                agg_field = aggs.get(field, {})
                buckets = agg_field.get("buckets", [])

                for bucket in buckets:
                    row[field] = bucket["key"]
                    parse_nested(bucket, depth + 1, row)
                    del row[field]

            parse_nested(result.get("aggregations", {}), 0, {})

        elif len(group_by) == 1:
            # Single field aggregation
            buckets = result.get("aggregations", {}).get("single_group", {}).get("buckets", [])
            for bucket in buckets:
                row = {group_by[0]: bucket["key"]}
                row[alias] = bucket.get(alias, {}).get("value", 0)
                if having and not self._check_having(row[alias], having):
                    continue
                # Attach time stats
                if ts_min is not None:
                    row["start_time"] = ts_min
                    row["end_time"] = ts_max
                    row["duration"] = ts_duration
                results.append(row)

        # Attach time stats to any existing results (nested aggs already appended)
        if ts_min is not None:
            for r in results:
                if "start_time" not in r:
                    r["start_time"] = ts_min
                    r["end_time"] = ts_max
                    r["duration"] = ts_duration

        return results

    def _check_having(self, value: Any, having: Dict) -> bool:
        """Check if value satisfies having condition"""
        op = having.get("operator", "gt")
        threshold = having.get("value", 0)

        try:
            val = float(value)
            thresh = float(threshold)

            if op == "gt":
                return val > thresh
            elif op == "gte":
                return val >= thresh
            elif op == "lt":
                return val < thresh
            elif op == "lte":
                return val <= thresh
            elif op == "eq":
                return val == thresh

            return True
        except (ValueError, TypeError):
            return False

    def _merge_stage_results(
        self,
        stage_results: Dict[str, List[Dict]],
        stages: List[Dict],
        output_mapping: Dict
    ) -> List[Dict[str, Any]]:
        """Merge multi-stage results into final output"""
        if not stages:
            return []

        primary_stage_id = stages[0].get("id")
        primary_results = stage_results.get(primary_stage_id, [])

        if not primary_results:
            return []

        # Empty mapping: return primary stage results as-is
        if not output_mapping:
            return primary_results

        # Build lookup tables for subsequent stages
        stage_lookup_tables = {}
        for stage in stages[1:]:
            stage_id = stage.get("id")
            join = stage.get("join")
            if not join:
                continue
            local_field = join.get("local_field")
            if not local_field:
                continue

            lookup = {}
            for row in stage_results.get(stage_id, []):
                key = row.get(local_field)
                if key is not None:
                    lookup[key] = row

            stage_lookup_tables[stage_id] = {"lookup": lookup, "join": join}

        # Build final output
        # Preserve time stats from primary stage (start_time / end_time / duration)
        time_fields = ("start_time", "end_time", "duration")
        final_output = []
        for primary_row in primary_results:
            output_row = {}
            # Copy time fields from primary stage
            for tf in time_fields:
                if tf in primary_row:
                    output_row[tf] = primary_row[tf]
            for out_field, mapping in output_mapping.items():
                from_stage = mapping.get("from_stage")
                source_field = mapping.get("field")

                if from_stage == primary_stage_id:
                    output_row[out_field] = primary_row.get(source_field)
                elif from_stage in stage_lookup_tables:
                    lookup_info = stage_lookup_tables[from_stage]
                    join = lookup_info["join"]
                    lookup = lookup_info["lookup"]
                    remote_field = join.get("remote_field")
                    join_key = primary_row.get(remote_field)
                    matched_row = lookup.get(join_key, {})
                    output_row[out_field] = matched_row.get(source_field, 0)
                else:
                    output_row[out_field] = None

            final_output.append(output_row)

        return final_output

    def close(self):
        """Close ES client connection"""
        if self._client:
            try:
                self._client.close()
            except Exception:
                pass
            self._client = None
