"""
Parquet data layer for efficient columnar storage with schema validation.
Replaces CSV usage across the pipeline.
"""

import json
import logging
from pathlib import Path
from typing import Dict, List, Optional, Union, Any
from datetime import datetime
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
from pyarrow import Schema, Field, DataType

logger = logging.getLogger(__name__)


class SchemaEvolutionError(Exception):
    """Raised when schema drift is detected."""
    pass


class ParquetDataLayer:
    """
    Production-ready Parquet data layer with schema validation and evolution.
    """
    
    def __init__(self, base_path: Path):
        self.base_path = Path(base_path)
        self.base_path.mkdir(parents=True, exist_ok=True)
        self.schemas_path = self.base_path / "schemas"
        self.schemas_path.mkdir(exist_ok=True)
        
    def _get_schema_path(self, domain: str) -> Path:
        """Get path for schema definition file."""
        return self.schemas_path / f"{domain}_schema.json"
    
    def _get_data_path(self, domain: str, partition_key: Optional[str] = None) -> Path:
        """Get partitioned data path."""
        if partition_key:
            return self.base_path / domain / f"partition={partition_key}"
        return self.base_path / domain
    
    def register_schema(self, domain: str, schema: Schema, overwrite: bool = False) -> None:
        """Register and persist schema for a domain."""
        schema_path = self._get_schema_path(domain)
        
        if schema_path.exists() and not overwrite:
            existing_schema = self.get_schema(domain)
            if not schema.equals(existing_schema):
                raise SchemaEvolutionError(
                    f"Schema drift detected for domain '{domain}'. "
                    f"Use overwrite=True to force update or migrate data first."
                )
        
        # Serialize schema to JSON
        schema_dict = {
            "fields": [
                {
                    "name": field.name,
                    "type": str(field.type),
                    "nullable": field.nullable,
                    "metadata": dict(field.metadata) if field.metadata else {}
                }
                for field in schema
            ],
            "metadata": dict(schema.metadata) if schema.metadata else {},
            "registered_at": datetime.utcnow().isoformat()
        }
        
        with open(schema_path, 'w') as f:
            json.dump(schema_dict, f, indent=2)
        
        logger.info(f"Schema registered for domain '{domain}' with {len(schema)} fields")
    
    def get_schema(self, domain: str) -> Schema:
        """Load registered schema for domain."""
        schema_path = self._get_schema_path(domain)
        
        if not schema_path.exists():
            raise ValueError(f"No schema registered for domain '{domain}'")
        
        with open(schema_path, 'r') as f:
            schema_dict = json.load(f)
        
        fields = []
        for field_dict in schema_dict["fields"]:
            # Parse type string back to PyArrow type
            type_str = field_dict["type"]
            if type_str == "string":
                pa_type = pa.string()
            elif type_str == "int64":
                pa_type = pa.int64()
            elif type_str == "float64":
                pa_type = pa.float64()
            elif type_str == "bool":
                pa_type = pa.bool_()
            elif type_str.startswith("timestamp"):
                pa_type = pa.timestamp('us')
            else:
                # Default to string for unknown types
                pa_type = pa.string()
            
            fields.append(Field(
                field_dict["name"],
                pa_type,
                nullable=field_dict["nullable"],
                metadata=field_dict.get("metadata", {})
            ))
        
        return Schema(fields, metadata=schema_dict.get("metadata", {}))
    
    def write_parquet(
        self,
        data: Union[pd.DataFrame, pa.Table],
        domain: str,
        partition_key: Optional[str] = None,
        validate_schema: bool = True
    ) -> Dict[str, Any]:
        """
        Write data to Parquet with schema validation.
        
        Returns:
            Dict with write statistics
        """
        start_time = datetime.utcnow()
        
        # Convert to PyArrow table if needed
        if isinstance(data, pd.DataFrame):
            table = pa.Table.from_pandas(data)
        else:
            table = data
        
        # Schema validation
        if validate_schema:
            try:
                expected_schema = self.get_schema(domain)
                if not table.schema.equals(expected_schema):
                    # Log schema differences
                    diff = self._compare_schemas(table.schema, expected_schema)
                    logger.warning(f"Schema differences for domain '{domain}': {diff}")
                    
                    # Attempt to cast to expected schema
                    try:
                        table = table.cast(expected_schema)
                        logger.info(f"Successfully cast data to expected schema for domain '{domain}'")
                    except pa.ArrowTypeError as e:
                        raise SchemaEvolutionError(
                            f"Cannot cast data to expected schema for domain '{domain}': {e}"
                        )
            except ValueError:
                # No schema registered, register current one
                self.register_schema(domain, table.schema)
                logger.info(f"Auto-registered schema for new domain '{domain}'")
        
        # Write partitioned data
        data_path = self._get_data_path(domain, partition_key)
        data_path.mkdir(parents=True, exist_ok=True)
        
        file_path = data_path / f"data_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.parquet"
        
        pq.write_table(
            table,
            file_path,
            compression='snappy',
            use_dictionary=True,
            row_group_size=10000
        )
        
        end_time = datetime.utcnow()
        duration_ms = (end_time - start_time).total_seconds() * 1000
        
        stats = {
            "domain": domain,
            "partition_key": partition_key,
            "file_path": str(file_path),
            "num_rows": len(table),
            "num_columns": len(table.schema),
            "file_size_bytes": file_path.stat().st_size,
            "duration_ms": duration_ms,
            "compression": "snappy",
            "written_at": end_time.isoformat()
        }
        
        logger.info(f"Wrote {len(table)} rows to {file_path} in {duration_ms:.1f}ms")
        return stats
    
    def read_parquet(
        self,
        domain: str,
        partition_key: Optional[str] = None,
        columns: Optional[List[str]] = None
    ) -> pa.Table:
        """Read Parquet data with optional column projection."""
        data_path = self._get_data_path(domain, partition_key)
        
        if not data_path.exists():
            raise ValueError(f"No data found for domain '{domain}', partition '{partition_key}'")
        
        # Find all Parquet files in the path
        parquet_files = list(data_path.glob("*.parquet"))
        
        if not parquet_files:
            raise ValueError(f"No Parquet files found in {data_path}")
        
        # Read all files and concatenate
        tables = []
        for file_path in parquet_files:
            table = pq.read_table(file_path, columns=columns)
            tables.append(table)
        
        if len(tables) == 1:
            return tables[0]
        else:
            return pa.concat_tables(tables)
    
    def migrate_from_csv(
        self,
        csv_path: Path,
        domain: str,
        partition_column: Optional[str] = None,
        schema_overrides: Optional[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        """
        Migrate CSV data to Parquet with validation.
        
        Args:
            csv_path: Path to CSV file
            domain: Target domain name
            partition_column: Column to partition by
            schema_overrides: Manual type overrides
            
        Returns:
            Migration statistics
        """
        logger.info(f"Starting CSV to Parquet migration: {csv_path} -> {domain}")
        
        # Read CSV with basic type inference
        df = pd.read_csv(csv_path)
        original_count = len(df)
        
        # Apply schema overrides
        if schema_overrides:
            for col, dtype in schema_overrides.items():
                if col in df.columns:
                    if dtype == "category":
                        df[col] = df[col].astype('category')
                    elif dtype == "string":
                        df[col] = df[col].astype('string')
                    elif dtype == "datetime":
                        df[col] = pd.to_datetime(df[col])
        
        # Partition data if needed
        if partition_column and partition_column in df.columns:
            partitions = df[partition_column].unique()
            write_stats = []
            
            for partition_value in partitions:
                partition_df = df[df[partition_column] == partition_value]
                stats = self.write_parquet(
                    partition_df,
                    domain,
                    partition_key=str(partition_value)
                )
                write_stats.append(stats)
            
            total_written = sum(s["num_rows"] for s in write_stats)
        else:
            stats = self.write_parquet(df, domain)
            write_stats = [stats]
            total_written = stats["num_rows"]
        
        migration_stats = {
            "source_csv": str(csv_path),
            "target_domain": domain,
            "original_rows": original_count,
            "written_rows": total_written,
            "partitions_created": len(write_stats),
            "file_size_reduction": self._calculate_size_reduction(csv_path, write_stats),
            "migration_successful": original_count == total_written
        }
        
        logger.info(f"Migration completed: {original_count} -> {total_written} rows")
        return migration_stats
    
    def validate_data(self, domain: str) -> Dict[str, Any]:
        """Validate Parquet data integrity and basic statistics."""
        try:
            table = self.read_parquet(domain)
            
            # Basic statistics
            stats = {
                "domain": domain,
                "total_rows": len(table),
                "total_columns": len(table.schema),
                "column_names": table.schema.names,
                "null_counts": {},
                "validation_passed": True,
                "validated_at": datetime.utcnow().isoformat()
            }
            
            # Calculate null counts for each column
            for col_name in table.schema.names:
                col_data = table.column(col_name)
                null_count = col_data.null_count
                stats["null_counts"][col_name] = null_count
            
            logger.info(f"Validation passed for domain '{domain}': {len(table)} rows, {len(table.schema)} columns")
            return stats
            
        except Exception as e:
            logger.error(f"Validation failed for domain '{domain}': {e}")
            return {
                "domain": domain,
                "validation_passed": False,
                "error": str(e),
                "validated_at": datetime.utcnow().isoformat()
            }
    
    def _compare_schemas(self, schema1: Schema, schema2: Schema) -> Dict[str, Any]:
        """Compare two schemas and return differences."""
        diff = {
            "added_fields": [],
            "removed_fields": [],
            "type_changes": []
        }
        
        names1 = set(schema1.names)
        names2 = set(schema2.names)
        
        diff["added_fields"] = list(names1 - names2)
        diff["removed_fields"] = list(names2 - names1)
        
        # Check type changes for common fields
        common_fields = names1 & names2
        for field_name in common_fields:
            field1 = schema1.field(field_name)
            field2 = schema2.field(field_name)
            
            if not field1.type.equals(field2.type):
                diff["type_changes"].append({
                    "field": field_name,
                    "old_type": str(field2.type),
                    "new_type": str(field1.type)
                })
        
        return diff
    
    def _calculate_size_reduction(self, csv_path: Path, write_stats: List[Dict]) -> float:
        """Calculate file size reduction percentage."""
        csv_size = csv_path.stat().st_size
        parquet_size = sum(s["file_size_bytes"] for s in write_stats)
        
        if csv_size > 0:
            return ((csv_size - parquet_size) / csv_size) * 100
        return 0.0


# Predefined schemas for common domains
DICTIONARY_SCHEMA = pa.schema([
    pa.field("TABLE_NAME", pa.string(), nullable=False),
    pa.field("COLUMN_NAME", pa.string(), nullable=False),
    pa.field("COLUMN_DESCRIPTION_ENG", pa.string(), nullable=True),
    pa.field("COLUMN_DATA_TYPE", pa.string(), nullable=False),
    pa.field("MANDAOTRY_AML_Y_N", pa.string(), nullable=True),
    pa.field("MANDAOTRY_RISK_ASSESMENTS_Y_N", pa.string(), nullable=True),
    pa.field("MANDATORY_FATCA_Y_N", pa.string(), nullable=True),
    pa.field("MANDATORY_GATCA_Y_N", pa.string(), nullable=True),
    pa.field("MANDAOTRY_GOAML_Y_N", pa.string(), nullable=True),
])

EMBEDDINGS_METADATA_SCHEMA = pa.schema([
    pa.field("doc_id", pa.string(), nullable=False),
    pa.field("table_name", pa.string(), nullable=False),
    pa.field("entity_type", pa.string(), nullable=False),
    pa.field("content_hash", pa.string(), nullable=False),
    pa.field("embedding_model", pa.string(), nullable=False),
    pa.field("embedding_dimension", pa.int64(), nullable=False),
    pa.field("created_at", pa.timestamp('us'), nullable=False),
])