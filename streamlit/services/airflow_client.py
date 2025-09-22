# services/airflow_client.py
import requests
import logging
from datetime import datetime
from config.settings import AIRFLOW_CONFIG

logger = logging.getLogger(__name__)

class AirflowClient:
    """Client for Airflow API interactions"""
    
    def __init__(self):
        self.base_url = AIRFLOW_CONFIG['base_url']
        self.username = AIRFLOW_CONFIG['username']
        self.password = AIRFLOW_CONFIG['password']
        self.auth = (self.username, self.password)
        self.timeout = AIRFLOW_CONFIG['timeout']
    
    def trigger_dag(self, dag_id: str, conf: dict) -> dict:
        """Trigger DAG via Airflow API"""
        url = f"{self.base_url}/dags/{dag_id}/dagRuns"
        
        payload = {
            "conf": conf,
            "dag_run_id": f"manual_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{conf.get('sample_id', 'unknown')}"
        }
        
        try:
            response = requests.post(
                url,
                json=payload,
                auth=self.auth,
                headers={'Content-Type': 'application/json'},
                timeout=self.timeout
            )
            
            if response.status_code in [200, 201]:
                data = response.json()
                return {
                    'success': True,
                    'dag_run_id': data['dag_run_id'],
                    'execution_date': data.get('execution_date'),
                    'state': data.get('state', 'queued')
                }
            elif response.status_code == 404:
                return {
                    'success': False,
                    'error': f"DAG '{dag_id}' not found. Make sure the DAG exists and is enabled."
                }
            elif response.status_code == 401:
                return {
                    'success': False,
                    'error': "Authentication failed. Check Airflow credentials."
                }
            else:
                logger.error(f"Airflow trigger failed: {response.status_code} - {response.text}")
                return {
                    'success': False,
                    'error': f"HTTP {response.status_code}: {response.text[:200]}"
                }
                
        except requests.exceptions.ConnectionError:
            return {
                'success': False,
                'error': "Cannot connect to Airflow service. Check if Airflow is running."
            }
        except requests.exceptions.Timeout:
            return {
                'success': False,
                'error': "Airflow request timed out"
            }
        except Exception as e:
            logger.error(f"Unexpected error triggering DAG: {e}")
            return {
                'success': False,
                'error': f"Unexpected error: {str(e)}"
            }
    
    def get_dag_run_status(self, dag_id: str, dag_run_id: str) -> dict:
        """Get DAG run status"""
        url = f"{self.base_url}/dags/{dag_id}/dagRuns/{dag_run_id}"
        
        try:
            response = requests.get(url, auth=self.auth, timeout=self.timeout)
            
            if response.status_code == 200:
                data = response.json()
                state = data.get('state', 'unknown')
                
                # Get current task information
                current_task = self._get_current_task(dag_id, dag_run_id)
                
                return {
                    'success': True,
                    'state': state,
                    'status': state,  # Add status field for compatibility
                    'current_task': current_task,
                    'start_date': data.get('start_date'),
                    'end_date': data.get('end_date'),
                    'execution_date': data.get('execution_date'),
                    'dag_id': data.get('dag_id'),
                    'dag_run_id': data.get('dag_run_id')
                }
            elif response.status_code == 404:
                return {
                    'success': False, 
                    'error': f"DAG run not found: {dag_run_id}"
                }
            else:
                return {
                    'success': False, 
                    'error': f"HTTP {response.status_code}: {response.text}"
                }
                
        except Exception as e:
            logger.error(f"Error getting DAG run status: {e}")
            return {'success': False, 'error': str(e)}

    def _get_current_task(self, dag_id: str, dag_run_id: str) -> str:
        """Get current running task for a DAG run"""
        url = f"{self.base_url}/dags/{dag_id}/dagRuns/{dag_run_id}/taskInstances"
        
        try:
            response = requests.get(url, auth=self.auth, timeout=self.timeout)
            if response.status_code == 200:
                data = response.json()
                task_instances = data.get('task_instances', [])
                
                # Find running task
                for task in task_instances:
                    if task.get('state') == 'running':
                        return task.get('task_id', 'unknown')
                
                # Find most recent task
                if task_instances:
                    latest_task = max(task_instances, 
                                    key=lambda x: x.get('start_date', ''), 
                                    default={})
                    return latest_task.get('task_id', 'unknown')
                
            return 'unknown'
        except Exception:
            return 'unknown'

    def get_dag_run_logs(self, dag_id: str, dag_run_id: str) -> dict:
        """Get logs for all tasks in a DAG run"""
        url = f"{self.base_url}/dags/{dag_id}/dagRuns/{dag_run_id}/taskInstances"
        
        try:
            response = requests.get(url, auth=self.auth, timeout=self.timeout)
            
            if response.status_code == 200:
                data = response.json()
                task_instances = data.get('task_instances', [])
                
                logs = {}
                for task in task_instances:
                    task_id = task.get('task_id')
                    if task_id:
                        task_logs = self._get_task_logs(dag_id, dag_run_id, task_id)
                        logs[task_id] = task_logs
                
                return {
                    'success': True,
                    'logs': logs
                }
            else:
                return {
                    'success': False,
                    'error': f"Failed to get task instances: {response.status_code}"
                }
                
        except Exception as e:
            logger.error(f"Error getting DAG run logs: {e}")
            return {
                'success': False,
                'error': str(e)
            }

    def _get_task_logs(self, dag_id: str, dag_run_id: str, task_id: str, try_number: int = 1) -> str:
        """Get logs for a specific task"""
        url = f"{self.base_url}/dags/{dag_id}/dagRuns/{dag_run_id}/taskInstances/{task_id}/logs/{try_number}"
        
        try:
            response = requests.get(url, auth=self.auth, timeout=self.timeout)
            if response.status_code == 200:
                # Try to get text content, fallback to JSON if needed
                try:
                    return response.text
                except:
                    data = response.json()
                    return data.get('content', 'No log content available')
            else:
                return f"Failed to fetch logs (HTTP {response.status_code})"
        except Exception as e:
            return f"Error fetching logs: {str(e)}"

    def stop_dag_run(self, dag_id: str, dag_run_id: str) -> dict:
        """Stop/cancel a DAG run"""
        url = f"{self.base_url}/dags/{dag_id}/dagRuns/{dag_run_id}"
        
        payload = {
            "state": "failed"  # Set state to failed to stop the run
        }
        
        try:
            response = requests.patch(
                url,
                json=payload,
                auth=self.auth,
                headers={'Content-Type': 'application/json'},
                timeout=self.timeout
            )
            
            if response.status_code == 200:
                return {
                    'success': True,
                    'message': f"DAG run {dag_run_id} stopped successfully"
                }
            elif response.status_code == 404:
                return {
                    'success': False,
                    'error': f"DAG run not found: {dag_run_id}"
                }
            else:
                return {
                    'success': False,
                    'error': f"Failed to stop DAG run: HTTP {response.status_code}"
                }
                
        except Exception as e:
            logger.error(f"Error stopping DAG run: {e}")
            return {
                'success': False,
                'error': str(e)
            }

    def test_connection(self) -> dict:
        """Test Airflow connection"""
        url = f"{self.base_url}/dags"
        
        try:
            response = requests.get(url, auth=self.auth, timeout=10)
            if response.status_code == 200:
                return {'success': True, 'message': 'Airflow connection successful'}
            elif response.status_code == 401:
                return {'success': False, 'error': 'Authentication failed - check credentials'}
            elif response.status_code == 404:
                return {'success': False, 'error': 'Airflow API not found - check URL'}
            else:
                return {'success': False, 'error': f"HTTP {response.status_code}: {response.text[:100]}"}
        except requests.exceptions.ConnectionError:
            return {'success': False, 'error': 'Cannot connect to Airflow - service may be down'}
        except requests.exceptions.Timeout:
            return {'success': False, 'error': 'Connection timeout - Airflow may be slow to respond'}
        except Exception as e:
            return {'success': False, 'error': f'Unexpected error: {str(e)}'}
    
    def get_dags(self) -> dict:
        """Get list of available DAGs"""
        url = f"{self.base_url}/dags"
        
        try:
            response = requests.get(url, auth=self.auth, timeout=10)
            if response.status_code == 200:
                data = response.json()
                return {
                    'success': True,
                    'dags': data.get('dags', [])
                }
            else:
                return {
                    'success': False,
                    'error': f"HTTP {response.status_code}: {response.text}"
                }
        except Exception as e:
            return {'success': False, 'error': str(e)}

    def get_dag_info(self, dag_id: str) -> dict:
        """Get information about a specific DAG"""
        url = f"{self.base_url}/dags/{dag_id}"
        
        try:
            response = requests.get(url, auth=self.auth, timeout=10)
            if response.status_code == 200:
                data = response.json()
                return {
                    'success': True,
                    'dag_info': data
                }
            elif response.status_code == 404:
                return {
                    'success': False,
                    'error': f"DAG '{dag_id}' not found"
                }
            else:
                return {
                    'success': False,
                    'error': f"HTTP {response.status_code}: {response.text}"
                }
        except Exception as e:
            return {'success': False, 'error': str(e)}

    def get_recent_dag_runs(self, dag_id: str, limit: int = 10) -> dict:
        """Get recent DAG runs for a specific DAG"""
        url = f"{self.base_url}/dags/{dag_id}/dagRuns"
        params = {
            'limit': limit,
            'order_by': '-execution_date'
        }
        
        try:
            response = requests.get(url, auth=self.auth, params=params, timeout=self.timeout)
            if response.status_code == 200:
                data = response.json()
                return {
                    'success': True,
                    'dag_runs': data.get('dag_runs', [])
                }
            else:
                return {
                    'success': False,
                    'error': f"HTTP {response.status_code}: {response.text}"
                }
        except Exception as e:
            return {'success': False, 'error': str(e)}