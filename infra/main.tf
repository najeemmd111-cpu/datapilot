terraform {
  required_providers {
    google = { source = "hashicorp/google", version = ">= 6.0" }
  }
}

variable "project_id" { type = string }

provider "google" {
  project = var.project_id
  region  = "europe-west1"
}

resource "google_bigquery_dataset" "datapilot" {
  dataset_id = "datapilot"
  location   = "EU"
}

# The API runs as this account. It can read data and run queries, but it can't write.
resource "google_service_account" "api" {
  account_id   = "datapilot-api"
  display_name = "DataPilot API (read-only)"
}

resource "google_bigquery_dataset_iam_member" "viewer" {
  dataset_id = google_bigquery_dataset.datapilot.dataset_id
  role       = "roles/bigquery.dataViewer"
  member     = "serviceAccount:${google_service_account.api.email}"
}

resource "google_project_iam_member" "job_user" {
  project = var.project_id
  role    = "roles/bigquery.jobUser"
  member  = "serviceAccount:${google_service_account.api.email}"
}

output "service_account" { value = google_service_account.api.email }
