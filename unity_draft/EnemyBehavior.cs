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
        BossStub,
        BossMistweaver,
        BossMemoryDevourer,
        BossTwinMain,
        BossTwinPartner
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
        public BulletPool bulletPool;

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
        public GameObject fuseVfx;
        public AudioClip fuseSfx;
        public Color fuseFlashColor = Color.red;
        public float fuseFlashSpeed = 10f;
        private SpriteRenderer _sr;
        private Color _baseColor;

        [Header("Buffer")]
        public float buffRadius = 3f;
        public float buffSpeedMult = 1.15f;
        public float buffDuration = 3f;
        public int buffMaxStacks = 3;
        public GameObject buffVfx;

        [Header("Splinter")]
        public string splinterTypeId = "splinterling";
        public int splinterCount = 2;
        public float splinterSpeedMult = 1.2f;
        public float splinterAttackMult = 0.7f;
        public float splinterHpMult = 0.5f;
        public int splinterSpoils = 0;
        public EnemyBehaviorType splinterBehavior = EnemyBehaviorType.SuicideFuse;

        [Header("Bandit")]
        public float stealRadius = 1.2f;
        public float fleeDuration = 2.0f;
        public float fleeSpeedMult = 1.4f;
        public int stealCoins = 3;
        public int stealEscalation = 2;
        public int stealMax = 12;
        public bool stealBanked = false; // steal from meta bank if allowed
        public MetaProgression meta;
        public float dropChanceOnDeath = 0.5f;
        public GameObject coinPrefab;
        private bool _fleeing;
        private float _fleeTimer;
        private Vector2 _fleeDir;

        [Header("Boss Stub")]
        public float phaseDuration = 6f;
        private float _phaseTimer;
        private bool _phaseDash;

        [Header("Boss Mistweaver")]
        public float mistTeleportInterval = 5f;
        public float mistVolleyInterval = 2.5f;
        public int mistVolleyProjectiles = 8;
        public float mistTeleportRange = 6f;
        private float _mistTeleportTimer;
        private float _mistVolleyTimer;

        [Header("Boss Memory Devourer")]
        public float devourerPulseInterval = 3f;
        public float devourerPulseRadius = 3f;
        public int devourerPulseDamage = 12;
        public float devourerSummonInterval = 7f;
        public string devourerSummonType = "basic";
        private float _devourerPulseTimer;
        private float _devourerSummonTimer;

        [Header("Twin Boss")]
        public EnemyBehavior twinPartner;
        public float twinEnrageMult = 1.3f;
        private bool _enraged;

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
            if (bulletPool == null) bulletPool = FindObjectOfType<BulletPool>();
            _sr = GetComponent<SpriteRenderer>();
            if (_sr != null) _baseColor = _sr.color;
            if (target == null)
            {
                var p = FindObjectOfType<Player>();
                if (p != null) target = p.transform;
            }
            if (_enemy != null) _enemy.OnKilled += HandleKilled;
            _phaseTimer = phaseDuration;
            if (meta == null) meta = FindObjectOfType<MetaProgression>();
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
                case EnemyBehaviorType.BossMistweaver:
                    UpdateMistweaver();
                    break;
                case EnemyBehaviorType.BossMemoryDevourer:
                    UpdateMemoryDevourer();
                    break;
                case EnemyBehaviorType.BossTwinMain:
                case EnemyBehaviorType.BossTwinPartner:
                    UpdateTwinBoss();
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
                if (fuseVfx != null) Instantiate(fuseVfx, transform.position, Quaternion.identity);
                if (fuseSfx != null) AudioSource.PlayClipAtPoint(fuseSfx, transform.position);
            }
            else if (_fuseTimer > 0f && dist > fuseRange * 1.25f)
            {
                // cancel fuse if target escapes
                _fuseTimer = -1f;
                if (_sr != null) _sr.color = _baseColor;
            }
            if (_fuseTimer >= 0f)
            {
                _fuseTimer -= Time.deltaTime;
                if (_sr != null)
                {
                    float t = Mathf.Abs(Mathf.Sin(Time.time * fuseFlashSpeed));
                    _sr.color = Color.Lerp(_baseColor, fuseFlashColor, t);
                }
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
            if (_sr != null) _sr.color = _baseColor;
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
                    var buff = e.GetComponent<ZGame.UnityDraft.Systems.BuffStatus>() ?? e.gameObject.AddComponent<ZGame.UnityDraft.Systems.BuffStatus>();
                    buff.ApplyBuff(buffSpeedMult, 1f, buffDuration, buffMaxStacks);
                    if (buffVfx != null)
                    {
                        var v = Object.Instantiate(buffVfx, e.transform.position, Quaternion.identity);
                        v.SetActive(true);
                    }
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
                    StealFromPlayer();
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

        private void StealFromPlayer()
        {
            if (meta == null) return;
            int stealAmt = Mathf.Clamp(stealCoins, 1, stealMax);
            if (stealBanked)
            {
                int taken = Mathf.Min(meta.bankedCoins, stealAmt);
                meta.SpendBankedCoins(taken);
                _enemy.spoils += taken;
            }
            else
            {
                int taken = Mathf.Min(meta.runCoins, stealAmt);
                meta.SpendRunCoins(taken);
                _enemy.spoils += taken;
            }
            stealCoins = Mathf.Min(stealMax, stealCoins + stealEscalation);
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

        private void UpdateMistweaver()
        {
            UpdateBossStub(); // reuse phase swap: dash vs ranged volley
            _mistTeleportTimer -= Time.deltaTime;
            _mistVolleyTimer -= Time.deltaTime;
            if (_mistTeleportTimer <= 0f)
            {
                _mistTeleportTimer = mistTeleportInterval;
                TeleportNearTarget();
            }
            if (_mistVolleyTimer <= 0f)
            {
                _mistVolleyTimer = mistVolleyInterval;
                RadialVolley(mistVolleyProjectiles, 360f);
            }
        }

        private void UpdateMemoryDevourer()
        {
            _devourerPulseTimer -= Time.deltaTime;
            _devourerSummonTimer -= Time.deltaTime;
            if (_devourerPulseTimer <= 0f)
            {
                _devourerPulseTimer = devourerPulseInterval;
                PulseAoE(devourerPulseRadius, devourerPulseDamage);
            }
            if (_devourerSummonTimer <= 0f)
            {
                _devourerSummonTimer = devourerSummonInterval;
                factory?.SpawnAround(devourerSummonType, transform.position);
            }
        }

        private void UpdateTwinBoss()
        {
            UpdateBossStub();
            if (_enraged || twinPartner == null) return;
            if (twinPartner._enemy == null || twinPartner._enemy.hp <= 0 || !twinPartner.gameObject.activeSelf)
            {
                _enraged = true;
                _enemy.speed *= twinEnrageMult;
                _enemy.attack = Mathf.RoundToInt(_enemy.attack * twinEnrageMult);
                if (shooter != null) shooter.fireCooldown *= 0.7f;
            }
        }

        private void HandleKilled()
        {
            if (behavior == EnemyBehaviorType.Splinter && factory != null)
            {
                for (int i = 0; i < splinterCount; i++)
                {
                    var child = factory.SpawnAround(splinterTypeId, transform.position);
                    if (child != null)
                    {
                        child.speed *= splinterSpeedMult;
                        child.attack = Mathf.Max(1, Mathf.RoundToInt(child.attack * splinterAttackMult));
                        child.hp = child.maxHp = Mathf.Max(1, Mathf.RoundToInt(child.maxHp * splinterHpMult));
                        child.spoils = splinterSpoils;
                        var beh = child.GetComponent<EnemyBehavior>();
                        if (beh != null && splinterBehavior != EnemyBehaviorType.None)
                        {
                            beh.behavior = splinterBehavior;
                        }
                    }
                }
            }
            if (behavior == EnemyBehaviorType.BossTwinMain && twinPartner != null)
            {
                twinPartner._enraged = true;
            }
            if (behavior == EnemyBehaviorType.Bandit)
            {
                if (Random.value < dropChanceOnDeath && coinPrefab != null && meta != null)
                {
                    var c = Instantiate(coinPrefab, transform.position, Quaternion.identity);
                    var cp = c.GetComponent<CoinPickup>();
                    if (cp != null)
                    {
                        cp.amount = stealCoins;
                        cp.meta = meta;
                    }
                }
            }
        }

        private void TeleportNearTarget()
        {
            if (target == null) return;
            Vector2 dir = Random.insideUnitCircle.normalized;
            Vector3 candidate = target.position + (Vector3)(dir * mistTeleportRange);
            transform.position = candidate;
        }

        private void RadialVolley(int count, float arcDeg)
        {
            if (bulletPool == null || bulletSystem == null) return;
            float step = arcDeg / count;
            for (int i = 0; i < count; i++)
            {
                float ang = step * i * Mathf.Deg2Rad;
                Vector2 dir = new Vector2(Mathf.Cos(ang), Mathf.Sin(ang));
                var b = bulletPool.Get();
                b.source = "enemy";
                b.faction = Bullet.Faction.Enemy;
                float dmg = _enemy != null ? _enemy.attack : 10;
                b.Init(transform.position, dir, dmg, range: 8f, speed: 420f);
                bulletSystem.RegisterBullet(b);
            }
        }

        private void PulseAoE(float radius, int damage)
        {
            var hits = Physics2D.OverlapCircleAll(transform.position, radius, bulletSystem != null ? bulletSystem.playerMask : LayerMask.GetMask("Player"));
            foreach (var h in hits)
            {
                var p = h.GetComponentInParent<Player>();
                if (p != null) p.Damage(damage);
            }
        }
    }
}
