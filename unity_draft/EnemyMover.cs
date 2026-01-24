using UnityEngine;

namespace ZGame.UnityDraft
{
    /// <summary>
    /// Basic chase/avoidance mover. Drafted from Python chase; extend with avoidance/anti-stuck later.
    /// </summary>
    [RequireComponent(typeof(Enemy))]
    public class EnemyMover : MonoBehaviour
    {
        public Transform target;
        public float avoidRadius = 0.4f; // in world units; keep small
        public float avoidForce = 1.0f;
        public float stuckThreshold = 0.1f;
        public float stuckTime = 0.5f;
        public float rePathInterval = 0.3f;

        private Enemy _enemy;
        private Rigidbody2D _rb;
        private Vector2 _lastPos;
        private float _stuckTimer;
        private float _repathTimer;

        private void Awake()
        {
            _enemy = GetComponent<Enemy>();
            _rb = GetComponent<Rigidbody2D>();
            _lastPos = transform.position;
        }

        private void FixedUpdate()
        {
            if (!_enemy || !_enemy.gameObject.activeSelf) return;
            Vector2 vel = Vector2.zero;
            if (target)
            {
                Vector2 dir = ((Vector2)target.position - (Vector2)transform.position).normalized;
                vel += dir;
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
            if (vel == Vector2.zero) return;
            float spd = _enemy.speed;
            Vector2 desired = vel.normalized * spd;
            if (_rb)
            {
                _rb.velocity = desired;
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
                    transform.position += (Vector3)(Random.insideUnitCircle * 0.2f);
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
    }
}
