"""Pydantic models for structured tool output.

These models define the response schemas for MCP tools, enabling
automatic JSON schema generation and output validation by MCP clients.
"""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

# --- Search Records ---


class SearchResult(BaseModel):
    """Result of a record search operation."""

    records: List[Dict[str, Any]] = Field(description="List of matching records")
    total: Optional[int] = Field(
        default=None, description="Total number of records matching the domain if requested"
    )
    limit: int = Field(description="Maximum records returned per page")
    offset: int = Field(description="Number of records skipped")
    model: str = Field(description="Odoo model name that was searched")


# --- Get Record ---


class FieldSelectionMetadata(BaseModel):
    """Metadata about which fields were returned and why."""

    fields_returned: int = Field(description="Number of fields in the response")
    field_selection_method: str = Field(
        description="How fields were selected (smart_defaults, explicit, all)"
    )
    total_fields_available: Optional[int] = Field(
        default=None, description="Total fields on the model"
    )
    note: Optional[str] = Field(
        default=None,
        description="Guidance on how to request more fields",
    )


class RecordResult(BaseModel):
    """Result of retrieving a single record by ID."""

    record: Dict[str, Any] = Field(description="Record data with requested fields")
    metadata: Optional[FieldSelectionMetadata] = Field(
        default=None,
        description="Field selection metadata (present when using smart defaults)",
    )


# --- List Models ---


class ModelOperations(BaseModel):
    """Allowed CRUD operations for a model."""

    read: bool = Field(description="Can read records")
    write: bool = Field(description="Can update records")
    create: bool = Field(description="Can create records")
    unlink: bool = Field(description="Can delete records")


class ModelInfo(BaseModel):
    """Information about an MCP-enabled Odoo model."""

    model: str = Field(description="Technical model name (e.g. 'res.partner')")
    name: str = Field(description="Human-readable model name")
    operations: Optional[ModelOperations] = Field(
        default=None, description="Allowed operations (standard mode only)"
    )


class ModelsResult(BaseModel):
    """Result of listing available models."""

    models: List[ModelInfo] = Field(description="List of available models")
    total: Optional[int] = Field(default=None, description="Total number of models")
    error: Optional[str] = Field(default=None, description="Error message if model listing failed")


# --- List Resource Templates ---


class ResourceTemplateParameter(BaseModel):
    """Parameter definition for a resource template."""

    model: str = Field(description="Odoo model name (e.g., res.partner)")
    record_id: Optional[str] = Field(default=None, description="Record ID (e.g., 10)")


class ResourceTemplateInfo(BaseModel):
    """Information about an available resource URI template."""

    uri_template: str = Field(description="URI template pattern")
    description: str = Field(description="What this resource provides")
    parameters: Dict[str, str] = Field(description="Template parameter descriptions")
    example: str = Field(description="Example URI")
    note: Optional[str] = Field(default=None, description="Additional usage notes")


class ResourceTemplatesResult(BaseModel):
    """Result of listing resource templates."""

    templates: List[ResourceTemplateInfo] = Field(description="Available resource templates")
    enabled_models: List[str] = Field(description="Sample of models usable with these templates")
    total_models: int = Field(description="Total number of enabled models")
    note: str = Field(description="Usage guidance for resources vs tools")


# --- Create Record ---


class CreateResult(BaseModel):
    """Result of creating a new record."""

    success: bool = Field(description="Whether the record was created successfully")
    record: Dict[str, Any] = Field(description="Essential fields of the created record")
    url: str = Field(description="Direct URL to the record in Odoo web interface")
    message: str = Field(description="Human-readable success message")


# --- Update Record ---


class UpdateResult(BaseModel):
    """Result of updating an existing record."""

    success: bool = Field(description="Whether the record was updated successfully")
    record: Dict[str, Any] = Field(description="Essential fields of the updated record")
    url: str = Field(description="Direct URL to the record in Odoo web interface")
    message: str = Field(description="Human-readable success message")


# --- Delete Record ---


class DeleteResult(BaseModel):
    """Result of deleting a record."""

    success: bool = Field(description="Whether the record was deleted successfully")
    deleted_id: int = Field(description="ID of the deleted record")
    deleted_name: str = Field(description="Display name of the deleted record")
    message: str = Field(description="Human-readable success message")


# --- Bulk Operations ---


class BulkCreateResult(BaseModel):
    """Result of bulk creating records."""

    success: bool = Field(description="Whether all records were created successfully")
    created_ids: List[int] = Field(description="IDs of the created records")
    count: int = Field(description="Number of records created")
    model: str = Field(description="Odoo model name")
    message: str = Field(description="Human-readable success message")


class BulkUpdateResult(BaseModel):
    """Result of bulk updating records."""

    success: bool = Field(description="Whether all records were updated successfully")
    updated_ids: List[int] = Field(description="IDs of the updated records")
    count: int = Field(description="Number of records updated")
    model: str = Field(description="Odoo model name")
    message: str = Field(description="Human-readable success message")


class BulkDeleteResult(BaseModel):
    """Result of bulk deleting records."""

    success: bool = Field(description="Whether all records were deleted successfully")
    deleted_ids: List[int] = Field(description="IDs of the deleted records")
    count: int = Field(description="Number of records deleted")
    model: str = Field(description="Odoo model name")
    message: str = Field(description="Human-readable success message")


# --- Public Config ---


class PublicConfigResult(BaseModel):
    """Safe public runtime configuration for MCP clients."""

    default_limit: int = Field(description="Default record limit when a tool call omits limit")
    max_limit: int = Field(description="Maximum record limit allowed for a single paged read")
    readonly: bool = Field(description="Whether write tools are disabled by server configuration")
    transport: str = Field(description="Configured MCP transport")
    api_version: str = Field(description="Configured Odoo API version")
    odoo_url: str = Field(description="Sanitized Odoo URL without credentials, query, or fragment")
    server_version: str = Field(description="MCP server version")
    runtime_id: str = Field(description="Server runtime identifier")
    max_bulk_size: int = Field(description="Maximum number of records allowed in one bulk write")
    max_smart_fields: int = Field(description="Maximum number of smart default fields returned")
    strict_security: bool = Field(description="Whether strict HTTP transport security is enabled")
    stateless_http: bool = Field(
        description="Whether streamable HTTP uses stateless per-request sessions"
    )


# --- Server Info ---


class ServerInfoResult(BaseModel):
    """Server version and connection status."""

    version: str = Field(description="MCP server version")
    git_commit: str = Field(description="Git commit hash of the running build")
    api_version: str = Field(description="Odoo API version (json2 or xmlrpc)")
    odoo_url: str = Field(description="Connected Odoo instance URL")
    connected: bool = Field(description="Whether the server is connected to Odoo")
    runtime_id: str = Field(description="Server runtime identifier")
    companies: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Available companies in the Odoo instance (id and name). Use company_id in search domains to filter by company.",
    )
    health: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Connection health details including reconnect and retry counters.",
    )


class ExecuteMethodResult(BaseModel):
    """Result of calling an arbitrary Odoo model method."""

    success: bool = Field(description="Whether the method call succeeded")
    model: str = Field(description="Odoo model name")
    method: str = Field(description="Method name that was called")
    result: Any = Field(description="Raw return value from the Odoo method")
    message: str = Field(description="Human-readable summary")


class OnchangeResult(BaseModel):
    """Result of an onchange simulation."""

    success: bool = Field(description="Whether the onchange call succeeded")
    model: str = Field(description="Odoo model name")
    method: str = Field(description="Method name (usually onchange)")
    value: Optional[Dict[str, Any]] = Field(
        default=None, description="Field values returned by onchange"
    )
    warning: Optional[Dict[str, Any]] = Field(
        default=None, description="Warning message returned by onchange"
    )
    domain: Optional[Dict[str, Any]] = Field(
        default=None, description="Domain restrictions returned by onchange"
    )
    message: str = Field(description="Human-readable summary")


class ModelMethodResult(BaseModel):
    """Result of discovering model methods."""

    model: str = Field(description="Odoo model name")
    methods: List[Dict[str, Any]] = Field(description="List of discovered methods")
    total: int = Field(description="Total number of methods found")
