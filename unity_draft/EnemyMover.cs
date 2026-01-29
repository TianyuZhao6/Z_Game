using UnityEngine;
using UnityEngine.AI;
using System.Collections.Generic;

namespace ZGame.UnityDraft
{
    /// <summary>
    /// Basic chase/avoidance mover. Drafted from Python chase; extend with avoidance/anti-stuck later.
    /// </summary>
    [RequireComponent(typeof(Enemy))]
    public class EnemyMover : MonoBehaviour
    {
        public bool useNavMeshAgent = false;
        public Transform target;
        public float avoidRadius = 0.4f; // in world units; keep small
        public float avoidForce = 1.0f;
        public float stuckThreshold = 0.1f;
        public float stuckTime = 0.5f;
        public float rePathInterval = 0.3f;
        [Tooltip("Random nudge distance when stuck.")]
        public float stuckNudge = 0.2f;
        [Header("Obstacle Avoidance")]
        public LayerMask obstacleMask;
        public float obstacleCheckDistance = 0.6f;
        public float obstacleAvoidForce = 1.5f;
        [Header("Pathfinding")]
        public bool usePathfinding = false;
        public Transform[] waypoints; // simple waypoint fallback if pathfinding is on
        private int _waypointIndex = 0;
        public GridManager gridManager;
        public bool[,] gridBlocked;
        public Vector2Int currentCell;
        private List<Vector2Int> _path = new();
        public float navRefreshInterval = 0.5f;
        private float _navRefreshTimer = 0f;
        [Tooltip("Rebuild grid automatically when navDirty is flagged on GridManager.")]
        public bool autoRefreshGrid = true;

        private Enemy _enemy;
        private Rigidbody2D _rb;
        private Nav.NavAgent2D _navAgent2D;
        private Vector2 _lastPos;
        private float _stuckTimer;
        private float _repathTimer;
        public Systems.WindBiomeModifier windModifier;
        private bool _subscribedNavDirty = false;
        public Nav.NavMesh2DStub navMesh2D;
        public NavMeshAgent navAgent3D;

        private void Awake()
        {
            _enemy = GetComponent<Enemy>();
            _rb = GetComponent<Rigidbody2D>();
            _navAgent2D = GetComponent<Nav.NavAgent2D>();
            navMesh2D = FindObjectOfType<Nav.NavMesh2DStub>();
#if UNITY_AI_NAVIGATION
            navAgent3D = GetComponent<NavMeshAgent>();
#endif
            _lastPos = transform.position;
        }

        private void OnDestroy()
        {
            if (_subscribedNavDirty && gridManager != null)
            {
                gridManager.OnNavDirty -= HandleNavDirty;
                _subscribedNavDirty = false;
            }
        }

        private void FixedUpdate()
        {
            if (!_enemy || !_enemy.gameObject.activeSelf) return;
            if (useNavMeshAgent && _navAgent2D != null && _navAgent2D.enabled)
            {
                if (_rb) _rb.velocity = Vector2.zero;
                return;
            }
#if UNITY_AI_NAVIGATION
            if (useNavMeshAgent && navAgent3D != null && navAgent3D.enabled)
            {
                if (target != null) navAgent3D.SetDestination(target.position);
                return;
            }
#endif
            Vector2 vel = Vector2.zero;
            if (target)
            {
                Vector2 dir = ((Vector2)target.position - (Vector2)transform.position).normalized;
                vel += dir;
            }
            else if (usePathfinding)
            {
                Vector3 dest = target ? target.position : transform.position;
                if (gridManager != null && gridBlocked != null)
                {
                    EnsureNavSubscription();
                    Vector2Int start = gridManager.WorldToGrid(transform.position);
                    Vector2Int goal = gridManager.WorldToGrid(dest);
                    _navRefreshTimer -= Time.fixedDeltaTime;
                    bool needsRefresh = gridManager.navDirty && autoRefreshGrid;
                    if (_repathTimer <= 0f || _path == null || _path.Count == 0 || needsRefresh || _navRefreshTimer <= 0f)
                    {
                        if (gridManager != null)
                        {
                            gridBlocked = gridManager.BuildBlockedGrid();
                        }
                        _path = Pathfinding.GridPathfinder.FindPath(gridBlocked, start, goal);
                        _repathTimer = rePathInterval;
                        _navRefreshTimer = navRefreshInterval;
                    }
                    if (_path != null && _path.Count > 1)
                    {
                        Vector2Int nextCell = _path[1];
                        Vector2 worldTarget = gridManager.GridToWorldCenter(nextCell);
                        Vector2 dir = (worldTarget - (Vector2)transform.position);
                        if (dir.magnitude < 0.1f)
                        {
                            _path.RemoveAt(0);
                        }
                        else
                        {
                            vel += dir.normalized;
                        }
                    }
                }
                else
                {
                    // fallback: waypoint loop
                    if (waypoints != null && waypoints.Length > 0)
                    {
                        Transform wp = waypoints[_waypointIndex % waypoints.Length];
                        Vector2 dir = ((Vector2)wp.position - (Vector2)transform.position);
                        if (dir.magnitude < 0.2f)
                        {
                            _waypointIndex = (_waypointIndex + 1) % waypoints.Length;
                        }
                        else
                        {
                            vel += dir.normalized;
                        }
                    }
                }
            }
            // Simple avoidance of nearby enemies
            if (avoidRadius > 0f && avoidForce > 0f)
            {
                Collider2D[] hits = Physics2D.OverlapCircleAll(transform.position, avoidRadius);
                foreach (var h in hits)
                {
                    if (h.attachedRigidbody == _rb) continue;
                    var other = h.GetComponent<Enemy>();
                    if (other == null) continue;
                    Vector2 away = (Vector2)(transform.position - other.transform.position);
                    if (away.sqrMagnitude > 0.0001f)
                        vel += away.normalized * avoidForce;
                }
            }
            // Obstacle avoidance using a simple raycast
            if (obstacleMask != 0 && obstacleCheckDistance > 0f && obstacleAvoidForce > 0f)
            {
                Vector2 fwd = vel.sqrMagnitude > 0.0001f ? vel.normalized : Vector2.right;
                RaycastHit2D hit = Physics2D.Raycast(transform.position, fwd, obstacleCheckDistance, obstacleMask);
                if (hit.collider != null)
                {
                    Vector2 perp = Vector2.Perpendicular(fwd);
                    // choose clearer side
                    bool leftClear = !Physics2D.Raycast(transform.position, perp, obstacleCheckDistance * 0.6f, obstacleMask);
                    bool rightClear = !Physics2D.Raycast(transform.position, -perp, obstacleCheckDistance * 0.6f, obstacleMask);
                    if (leftClear && !rightClear) vel += perp * obstacleAvoidForce;
                    else if (rightClear && !leftClear) vel -= perp * obstacleAvoidForce;
                    else vel += (Random.value > 0.5f ? perp : -perp) * obstacleAvoidForce;
                }
            }
            // Slight bias away from paint pools (tagged "Paint") if present
            var paints = Physics2D.OverlapCircleAll(transform.position, avoidRadius, LayerMask.GetMask("Default"));
            foreach (var p in paints)
            {
                if (p.CompareTag("Paint"))
                {
                    Vector2 away = (Vector2)(transform.position - p.transform.position);
                    if (away.sqrMagnitude > 0.0001f) vel += away.normalized * (avoidForce * 0.5f);
                }
            }
            if (vel == Vector2.zero) return;
            float spd = _enemy.speed;
            Vector2 desired = vel.normalized * spd;
            if (_rb)
            {
                _rb.velocity = desired;
                windModifier?.ApplyIfBiome(_enemy?.balance?.name, _rb);
            }
            else
            {
                transform.position += (Vector3)(desired * Time.fixedDeltaTime);
            }
            AntiStuck();
        }

        private void AntiStuck()
        {
            Vector2 curPos = transform.position;
            float moved = (curPos - _lastPos).magnitude;
            _lastPos = curPos;
            if (moved < stuckThreshold)
            {
                _stuckTimer += Time.fixedDeltaTime;
                if (_stuckTimer >= stuckTime)
                {
                    // small nudge
                    transform.position += (Vector3)(Random.insideUnitCircle * stuckNudge);
                    _stuckTimer = 0f;
                }
            }
            else
            {
                _stuckTimer = 0f;
            }
            _repathTimer += Time.fixedDeltaTime;
            if (_repathTimer >= rePathInterval)
            {
                _repathTimer = 0f;
            }
        }

        private void HandleNavDirty()
        {
            if (!autoRefreshGrid || gridManager == null) return;
            gridBlocked = gridManager.BuildBlockedGrid();
            if (navMesh2D != null) navMesh2D.MarkDirty();
            _repathTimer = 0f;
        }

        private void EnsureNavSubscription()
        {
            if (_subscribedNavDirty || gridManager == null) return;
            gridManager.OnNavDirty += HandleNavDirty;
            _subscribedNavDirty = true;
        }
    }
}
