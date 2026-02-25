output "project_name" {
  description = "Full resource name of the Lakebase project."
  value       = databricks_postgres_project.this.name
}

output "branch_names" {
  description = "Map of branch key → full resource name."
  value = {
    for k, b in databricks_postgres_branch.extra : k => b.name
  }
}

output "endpoint_names" {
  description = "Map of branch key → endpoint resource name."
  value = {
    for k, e in databricks_postgres_endpoint.extra : k => e.name
  }
}

output "manage_users" {
  description = "Users with CAN_MANAGE (read-write Postgres roles)."
  value       = var.manage_users
}

output "use_users" {
  description = "Users with CAN_USE (read-only Postgres roles)."
  value       = var.use_users
}
