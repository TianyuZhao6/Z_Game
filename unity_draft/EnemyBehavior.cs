using UnityEngine;
using System.Collections;
using ZGame.UnityDraft.Combat;
using ZGame.UnityDraft.Systems;

namespace ZGame.UnityDraft
{
    public enum EnemyBehaviorType
    {
        None,
        RavagerDash,
        RangedSpitter,
        SuicideFuse,
        Buffer,
        Shielder,
        Splinter,
        Bandit,
        BossStub
    }

    /// <summary>
    /// Behavior controller stubs for different enemy types: dash, ranged, suicide, buffer/shielder, splinter, bandit, boss.
    /// </summary>
    [RequireComponent(typeof(Enemy))]
    public class EnemyBehavior : MonoBehaviour
    {
        public EnemyBehaviorType behavior;
        public EnemyMover mover;
        public EnemyShooter shooter;
        public ShielderAura shielderAura;
        public EnemyFactory factory;
        public Transform target;
        public BulletCombatSystem bulletSystem;

        [Header("Dash (Ravager/Boss)")]
        public float dashInterval = 3f;
        public float dashDuration = 0.65f;
        public float dashSpeedMult = 2.2f;
        public ObstacleCrushOnContact crush;

        [Header("Suicide")]
        public float fuseRange = 1.6f;
        public float fuseTime = 1.0f;
        public float suicideDamage = 20f;
        private float _fuseTimer = -1f;

        [Header("Buffer")]
        public float buffRadius = 3f;
        public float buffSpeedMult = 1.15f;
        public float buffDuration = 3f;

        [Header("Splinter")]
        public string splinterTypeId = "splinterling";
        public int splinterCount = 2;

        [Header("Bandit")]
        public float stealRadius = 1.2f;
        public float fleeDuration = 2.0f;
        public float fleeSpeedMult = 1.4f;
        private bool _fleeing;
        private float _fleeTimer;
        private Vector2 _fleeDir;

        [Header("Boss Stub")]
        public float phaseDuration = 6f;
        private float _phaseTimer;
        private bool _phaseDash;

        private Enemy _enemy;
        private Rigidbody2D _rb;
        private float _dashTimer;

        private void Awake()
        {
            _enemy = GetComponent<Enemy>();
            _rb = GetComponent<Rigidbody2D>();
            if (mover == null) mover = GetComponent<EnemyMover>();
            if (shooter == null) shooter = GetComponent<EnemyShooter>();
            if (shielderAura == null) shielderAura = GetComponent<ShielderAura>();
            if (crush == null) crush = GetComponent<ObstacleCrushOnContact>();
            if (factory == null) factory = FindObjectOfType<EnemyFactory>();
            if (bulletSystem == null) bulletSystem = FindObjectOfType<BulletCombatSystem>();
            if (target == null)
            {
                var p = FindObjectOfType<Player>();
                if (p != null) target = p.transform;
            }
            if (_enemy != null) _enemy.OnKilled += HandleKilled;
            _phaseTimer = phaseDuration;
        }

        private void Update()
        {
            switch (behavior)
            {
                case EnemyBehaviorType.RavagerDash:
                    UpdateDash();
                    break;
                case EnemyBehaviorType.RangedSpitter:
                    if (shooter != null && target != null) shooter.target = target;
                    break;
                case EnemyBehaviorType.SuicideFuse:
                    UpdateFuse();
                    break;
                case EnemyBehaviorType.Buffer:
                    UpdateBuffer();
                    break;
                case EnemyBehaviorType.Shielder:
                    if (shielderAura != null) shielderAura.enabled = true;
                    break;
                case EnemyBehaviorType.Splinter:
                    // passive; handled on kill
                    break;
                case EnemyBehaviorType.Bandit:
                    UpdateBandit();
                    break;
                case EnemyBehaviorType.BossStub:
                    UpdateBossStub();
                    break;
            }
        }

        private void UpdateDash()
        {
            _dashTimer -= Time.deltaTime;
            if (_dashTimer <= 0f)
            {
                _dashTimer = dashInterval;
                StartCoroutine(DashRoutine());
            }
        }

        private System.Collections.IEnumerator DashRoutine()
        {
            float original = _enemy.speed;
            _enemy.speed = original * dashSpeedMult;
            if (crush != null) crush.isCrushing = true;
            float t = dashDuration;
            while (t > 0f)
            {
                t -= Time.deltaTime;
                yield return null;
            }
            _enemy.speed = original;
            if (crush != null) crush.isCrushing = false;
        }

        private void UpdateFuse()
        {
            if (target == null) return;
            float dist = Vector2.Distance(transform.position, target.position);
            if (_fuseTimer < 0f && dist <= fuseRange)
            {
                _fuseTimer = fuseTime;
            }
            if (_fuseTimer >= 0f)
            {
                _fuseTimer -= Time.deltaTime;
                if (_fuseTimer <= 0f)
                {
                    ExplodeSelf();
                }
            }
        }

        private void ExplodeSelf()
        {
            // Simple AoE: damage player if in range
            if (target != null)
            {
                float dist = Vector2.Distance(transform.position, target.position);
                if (dist <= fuseRange)
                {
                    var p = target.GetComponent<Player>();
                    if (p != null) p.Damage(Mathf.RoundToInt(suicideDamage));
                }
            }
            _enemy.Kill();
        }

        private void UpdateBuffer()
        {
            var hits = Physics2D.OverlapCircleAll(transform.position, buffRadius);
            foreach (var h in hits)
            {
                if (h.attachedRigidbody && h.attachedRigidbody.gameObject == gameObject) continue;
                var e = h.GetComponentInParent<Enemy>();
                if (e != null && e != _enemy)
                {
                    e.speed *= buffSpeedMult;
                }
            }
        }

        private void UpdateBandit()
        {
            if (_fleeing)
            {
                _fleeTimer -= Time.deltaTime;
                if (_rb != null) _rb.velocity = _fleeDir * _enemy.speed * fleeSpeedMult;
                if (_fleeTimer <= 0f)
                {
                    _fleeing = false;
                    if (_rb != null) _rb.velocity = Vector2.zero;
                    if (mover != null) mover.enabled = true;
                }
                return;
            }

            // steal nearby coins
            var hits = Physics2D.OverlapCircleAll(transform.position, stealRadius);
            foreach (var h in hits)
            {
                var coin = h.GetComponentInParent<CoinPickup>();
                if (coin != null)
                {
                    coin.Award();
                    _fleeing = true;
                    _fleeTimer = fleeDuration;
                    if (mover != null) mover.enabled = false;
                    if (target != null)
                    {
                        Vector2 away = (Vector2)(transform.position - target.position);
                        _fleeDir = away.sqrMagnitude > 0.01f ? away.normalized : Random.insideUnitCircle.normalized;
                    }
                    return;
                }
            }
        }

        private void UpdateBossStub()
        {
            _phaseTimer -= Time.deltaTime;
            if (_phaseTimer <= 0f)
            {
                _phaseTimer = phaseDuration;
                _phaseDash = !_phaseDash;
            }
            if (_phaseDash)
            {
                UpdateDash();
                if (shooter != null) shooter.enabled = false;
            }
            else
            {
                if (shooter != null)
                {
                    shooter.enabled = true;
                    shooter.target = target;
                }
            }
        }

        private void HandleKilled()
        {
            if (behavior == EnemyBehaviorType.Splinter && factory != null)
            {
                for (int i = 0; i < splinterCount; i++)
                {
                    factory.SpawnAround(splinterTypeId, transform.position);
                }
            }
        }
    }
}
