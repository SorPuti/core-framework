"""
PM2 deployment generator.

Generates ecosystem.config.js for PM2 process management.
"""

from __future__ import annotations

from pathlib import Path


def generate_pm2(output_dir: Path) -> None:
    """
    Generate PM2 deployment files.
    
    Creates:
        - ecosystem.config.js
    
    Args:
        output_dir: Directory to write files to
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    ecosystem = '''module.exports = {
  apps: [
    // ==========================================================================
    // API Server
    // ==========================================================================
    {
      name: "api",
      script: "core",
      args: "run --host 0.0.0.0 --port 8000 --no-reload",
      instances: "max",  // Use all available CPUs
      exec_mode: "cluster",
      autorestart: true,
      watch: false,
      max_memory_restart: "1G",
      env: {
        NODE_ENV: "production",
        ENVIRONMENT: "production",
        DEBUG: "false",
      },
      env_development: {
        NODE_ENV: "development",
        ENVIRONMENT: "development",
        DEBUG: "true",
      },
      // Graceful shutdown
      kill_timeout: 5000,
      wait_ready: true,
      listen_timeout: 10000,
    },

    // ==========================================================================
    // Background Worker
    // ==========================================================================
    {
      name: "worker",
      script: "core",
      args: "worker --queue default --concurrency 4",
      instances: 2,
      exec_mode: "fork",
      autorestart: true,
      watch: false,
      max_memory_restart: "512M",
      env: {
        NODE_ENV: "production",
        ENVIRONMENT: "production",
      },
    },

    // ==========================================================================
    // Task Scheduler
    // ==========================================================================
    {
      name: "scheduler",
      script: "core",
      args: "scheduler",
      instances: 1,  // Only one scheduler instance
      exec_mode: "fork",
      autorestart: true,
      watch: false,
      max_memory_restart: "256M",
      env: {
        NODE_ENV: "production",
        ENVIRONMENT: "production",
      },
    },

    // ==========================================================================
    // Event Consumer (optional - uncomment if needed)
    // ==========================================================================
    // {
    //   name: "consumer-orders",
    //   script: "core",
    //   args: "consumer --group order-service",
    //   instances: 2,
    //   exec_mode: "fork",
    //   autorestart: true,
    //   watch: false,
    //   max_memory_restart: "512M",
    //   env: {
    //     NODE_ENV: "production",
    //     ENVIRONMENT: "production",
    //   },
    // },
  ],

  // ==========================================================================
  // Deployment Configuration
  // ==========================================================================
  deploy: {
    production: {
      user: "deploy",
      host: ["server1.example.com", "server2.example.com"],
      ref: "origin/main",
      repo: "git@github.com:user/repo.git",
      path: "/var/www/app",
      "pre-deploy-local": "",
      "post-deploy": "uv sync && pm2 reload ecosystem.config.js --env production",
      "pre-setup": "",
      env: {
        NODE_ENV: "production",
      },
    },
    staging: {
      user: "deploy",
      host: "staging.example.com",
      ref: "origin/develop",
      repo: "git@github.com:user/repo.git",
      path: "/var/www/app-staging",
      "post-deploy": "uv sync && pm2 reload ecosystem.config.js --env staging",
      env: {
        NODE_ENV: "staging",
      },
    },
  },
};
'''
    
    # Write file
    (output_dir / "ecosystem.config.js").write_text(ecosystem)
