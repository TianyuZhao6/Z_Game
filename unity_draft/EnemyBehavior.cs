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
        [System.Serializable]
        public enum BossAttackType { Pause, Teleport, Volley, Spiral, Fog, Hazard, Summon, Clone, AimedBurst, RingHazard }
        [System.Serializable]
        public class BossAttackStep
        {
            public BossAttackType type = BossAttackType.Pause;
            public float duration = 1f;
            public int intParam = 0;
            public float floatParam = 0f;
            public float floatParam2 = 0f;
            public float floatParam3 = 0f;
        }

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
        public ZGame.UnityDraft.VFX.VfxPlayer vfxPlayer;
        public ZGame.UnityDraft.VFX.SfxPlayer sfxPlayer;

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
        public float mistFogInterval = 4f;
        public float mistFogRadius = 2.2f;
        public float mistFogDuration = 5f;
        public Color mistFogColor = new Color(0.6f, 0.8f, 1f, 0.35f);
        public float mistSpiralStepDeg = 18f;
        public string mistCloneTypeId = "mist_clone";
        private int _mistPhase = 0;
        private float _mistTeleportTimer;
        private float _mistVolleyTimer;
        private float _mistFogTimer;
        private float _mistSpiralAngle;

        [Header("Boss Memory Devourer")]
        public float devourerPulseInterval = 3f;
        public float devourerPulseRadius = 3f;
        public int devourerPulseDamage = 12;
        public float devourerSummonInterval = 7f;
        public string devourerSummonType = "basic";
        public float devourerSpiralInterval = 2.2f;
        public int devourerSpiralProjectiles = 10;
        public float devourerSpiralStepDeg = 12f;
        public float devourerHazardInterval = 5f;
        public float devourerHazardRadius = 2.4f;
        public float devourerHazardDuration = 6f;
        public Color devourerHazardColor = new Color(0.8f, 0.2f, 0.2f, 0.35f);
        private float _devourerPulseTimer;
        private float _devourerSummonTimer;
        private float _devourerSpiralTimer;
        private float _devourerSpiralAngle;
        private float _devourerHazardTimer;

        [Header("Twin Boss")]
        public EnemyBehavior twinPartner;
        public float twinEnrageMult = 1.3f;
        public float twinVolleyInterval = 3.5f;
        public int twinVolleyCount = 6;
        private float _twinVolleyTimer;
        private bool _enraged;

        [Header("Scripted Sequences")]
        public bool useScriptedPattern = false;
        public BossAttackStep[] mistPattern;
        public BossAttackStep[] devourerPattern;
        public BossAttackStep[] twinPattern;
        [Header("Phase Patterns (optional)")]
        public BossAttackStep[] mistPhase0Pattern;
        public BossAttackStep[] mistPhase1Pattern;
        public BossAttackStep[] mistPhase2Pattern;
        public BossAttackStep[] devourerPhase0Pattern;
        public BossAttackStep[] devourerPhase1Pattern;
        public BossAttackStep[] devourerPhase2Pattern;
        public BossAttackStep[] twinPhase0Pattern;
        public BossAttackStep[] twinEnragePattern;
        private Coroutine _patternRoutine;
        [Header("Default Pattern (Python-inspired)")]
        public bool useDefaultPattern = true;
        [Header("Aimed Burst Settings")]
        public int aimedBurstProjectiles = 5;
        public float aimedBurstSpreadDeg = 20f;
        public float aimedBurstSpeed = 520f;

        [Header("Ring Hazard Settings")]
        public int ringHazardCount = 6;
        public float ringHazardRadius = 4f;

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
            if (vfxPlayer == null) vfxPlayer = FindObjectOfType<ZGame.UnityDraft.VFX.VfxPlayer>();
            if (sfxPlayer == null) sfxPlayer = FindObjectOfType<ZGame.UnityDraft.VFX.SfxPlayer>();
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
            if (useScriptedPattern && _patternRoutine == null)
            {
                if (useDefaultPattern) SeedDefaultPatterns();
                _patternRoutine = StartCoroutine(RunPattern());
            }
        }

        private void Update()
        {
            if (useScriptedPattern) return; // pattern coroutine drives actions
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

        private void UpdatePhase()
        {
            if (_enemy == null || _enemy.maxHp <= 0) return;
            float hpFrac = _enemy.hp / (float)_enemy.maxHp;
            int phase = 0;
            if (hpFrac <= 0.66f) phase = 1;
            if (hpFrac <= 0.33f) phase = 2;
            if (behavior == EnemyBehaviorType.BossMistweaver)
            {
                _mistPhase = phase;
            }
            if (behavior == EnemyBehaviorType.BossMemoryDevourer)
            {
                _enraged = phase >= 2;
            }
            if ((behavior == EnemyBehaviorType.BossTwinMain || behavior == EnemyBehaviorType.BossTwinPartner) && !_enraged && hpFrac <= 0.5f)
            {
                _enraged = true;
                _enemy.speed *= twinEnrageMult;
                _enemy.attack = Mathf.RoundToInt(_enemy.attack * twinEnrageMult);
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
                if (vfxPlayer != null && fuseVfx != null) vfxPlayer.Play(fuseVfx.name, transform.position);
                else if (fuseVfx != null) Instantiate(fuseVfx, transform.position, Quaternion.identity);
                if (sfxPlayer != null && fuseSfx != null) sfxPlayer.Play(fuseSfx.name, transform.position);
                else if (fuseSfx != null) AudioSource.PlayClipAtPoint(fuseSfx, transform.position);
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
            UpdatePhase();
            UpdateBossStub(); // reuse phase swap: dash vs ranged volley
            _mistTeleportTimer -= Time.deltaTime;
            _mistVolleyTimer -= Time.deltaTime;
            _mistFogTimer -= Time.deltaTime;
            if (_mistTeleportTimer <= 0f)
            {
                _mistTeleportTimer = mistTeleportInterval;
                TeleportNearTarget();
                if (_mistPhase >= 1) SpawnMistClone();
            }
            if (_mistVolleyTimer <= 0f)
            {
                _mistVolleyTimer = mistVolleyInterval;
                float arc = _mistPhase >= 2 ? 360f : 180f;
                RadialVolley(mistVolleyProjectiles, arc);
            }
            if (_mistFogTimer <= 0f)
            {
                _mistFogTimer = mistFogInterval;
                SpawnMistFog();
            }
            // slow spiral volley
            _mistSpiralAngle += mistSpiralStepDeg * Time.deltaTime * 10f;
            if (_mistPhase >= 1) SpiralVolley(mistVolleyProjectiles, mistSpiralStepDeg, ref _mistSpiralAngle);
        }

        private void UpdateMemoryDevourer()
        {
            UpdatePhase();
            _devourerPulseTimer -= Time.deltaTime;
            _devourerSummonTimer -= Time.deltaTime;
            _devourerSpiralTimer -= Time.deltaTime;
            _devourerHazardTimer -= Time.deltaTime;
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
            if (_devourerSpiralTimer <= 0f)
            {
                _devourerSpiralTimer = devourerSpiralInterval;
                SpiralVolley(devourerSpiralProjectiles, devourerSpiralStepDeg, ref _devourerSpiralAngle);
            }
            if (_devourerHazardTimer <= 0f)
            {
                _devourerHazardTimer = devourerHazardInterval;
                DropHazard();
            }
        }

        private void UpdateTwinBoss()
        {
            UpdateBossStub();
            _twinVolleyTimer -= Time.deltaTime;
            if (!_enraged && _twinVolleyTimer <= 0f && twinPartner != null && twinPartner.gameObject.activeSelf && twinPartner._enemy != null && twinPartner._enemy.hp > 0)
            {
                _twinVolleyTimer = twinVolleyInterval;
                // crossfire: both fire offset volleys
                RadialVolley(twinVolleyCount, 120f);
                if (twinPartner.shooter != null && twinPartner.target != null)
                {
                    twinPartner.RadialVolley(twinVolleyCount, 120f);
                }
            }
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
                float spd = _mistPhase >= 2 ? 520f : 420f;
                b.Init(transform.position, dir, dmg, range: 10f, speed: spd);
                bulletSystem.RegisterBullet(b);
            }
        }

        private void SpiralVolley(int count, float stepDeg, ref float angleOffset)
        {
            if (bulletPool == null || bulletSystem == null) return;
            float ang = angleOffset;
            for (int i = 0; i < count; i++)
            {
                float a = (ang + i * stepDeg) * Mathf.Deg2Rad;
                Vector2 dir = new Vector2(Mathf.Cos(a), Mathf.Sin(a));
                var b = bulletPool.Get();
                b.source = "enemy";
                b.faction = Bullet.Faction.Enemy;
                float dmg = _enemy != null ? _enemy.attack * 0.8f : 8f;
                b.Init(transform.position, dir, dmg, range: 10f, speed: 360f);
                bulletSystem.RegisterBullet(b);
            }
            angleOffset += stepDeg * 0.5f;
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

        private void SpawnMistFog()
        {
            var paint = FindObjectOfType<PaintSystem>();
            if (paint != null)
            {
                paint.SpawnEnemyPaint(transform.position, mistFogRadius, mistFogDuration, mistFogColor);
            }
        }

        private BossAttackStep[] CurrentPattern()
        {
            switch (behavior)
            {
                case EnemyBehaviorType.BossMistweaver:
                    if (_mistPhase >= 2 && mistPhase2Pattern != null && mistPhase2Pattern.Length > 0) return mistPhase2Pattern;
                    if (_mistPhase >= 1 && mistPhase1Pattern != null && mistPhase1Pattern.Length > 0) return mistPhase1Pattern;
                    if (mistPhase0Pattern != null && mistPhase0Pattern.Length > 0) return mistPhase0Pattern;
                    return mistPattern;
                case EnemyBehaviorType.BossMemoryDevourer:
                    if (_enraged && devourerPhase2Pattern != null && devourerPhase2Pattern.Length > 0) return devourerPhase2Pattern;
                    if (devourerPhase1Pattern != null && devourerPhase1Pattern.Length > 0) return devourerPhase1Pattern;
                    if (devourerPhase0Pattern != null && devourerPhase0Pattern.Length > 0) return devourerPhase0Pattern;
                    return devourerPattern;
                case EnemyBehaviorType.BossTwinMain:
                case EnemyBehaviorType.BossTwinPartner:
                    if (_enraged && twinEnragePattern != null && twinEnragePattern.Length > 0) return twinEnragePattern;
                    if (twinPhase0Pattern != null && twinPhase0Pattern.Length > 0) return twinPhase0Pattern;
                    return twinPattern;
                default:
                    return null;
            }
        }

        private void SpawnMistClone()
        {
            if (factory == null || string.IsNullOrEmpty(mistCloneTypeId)) return;
            factory.SpawnAround(mistCloneTypeId, transform.position);
        }

        private void DropHazard()
        {
            var paint = FindObjectOfType<PaintSystem>();
            if (paint != null)
            {
                paint.SpawnEnemyPaint(transform.position, devourerHazardRadius, devourerHazardDuration, devourerHazardColor);
            }
        }

        private void AimedBurst(int count, float spreadDeg, float speedOverride)
        {
            if (bulletPool == null || bulletSystem == null || target == null) return;
            Vector2 baseDir = (target.position - transform.position);
            if (baseDir.sqrMagnitude < 0.01f) baseDir = Vector2.right;
            baseDir.Normalize();
            float start = -spreadDeg * 0.5f;
            for (int i = 0; i < count; i++)
            {
                float t = count == 1 ? 0f : i / (float)(count - 1);
                float ang = start + spreadDeg * t;
                Vector2 d = Quaternion.Euler(0, 0, ang) * baseDir;
                var b = bulletPool.Get();
                b.source = "enemy";
                b.faction = Bullet.Faction.Enemy;
                float dmg = _enemy != null ? _enemy.attack : 10;
                b.Init(transform.position, d.normalized, dmg, range: 12f, speed: speedOverride);
                bulletSystem.RegisterBullet(b);
            }
        }

        private void RingHazard(int count, float radius)
        {
            var paint = FindObjectOfType<PaintSystem>();
            if (paint == null) return;
            float step = 360f / Mathf.Max(1, count);
            for (int i = 0; i < count; i++)
            {
                float ang = step * i * Mathf.Deg2Rad;
                Vector3 pos = transform.position + new Vector3(Mathf.Cos(ang), Mathf.Sin(ang), 0f) * radius;
                paint.SpawnEnemyPaint(pos, devourerHazardRadius, devourerHazardDuration, devourerHazardColor);
            }
        }

        private IEnumerator RunPattern()
        {
            while (useScriptedPattern)
            {
                var seq = CurrentPattern();
                if (seq == null || seq.Length == 0) yield return null;
                foreach (var step in seq)
                {
                    yield return ExecuteStep(step);
                }
            }
        }

        private void SeedDefaultPatterns()
        {
            if (behavior == EnemyBehaviorType.BossMistweaver && (mistPattern == null || mistPattern.Length == 0))
            {
                mistPhase0Pattern = new BossAttackStep[]
                {
                    new BossAttackStep{ type=BossAttackType.Teleport, duration=0.3f },
                    new BossAttackStep{ type=BossAttackType.AimedBurst, intParam=5, floatParam=18f, floatParam2=500f, duration=0.4f },
                    new BossAttackStep{ type=BossAttackType.Volley, intParam=8, floatParam=180f, duration=0.55f },
                    new BossAttackStep{ type=BossAttackType.Pause, duration=0.45f }
                };
                mistPhase1Pattern = new BossAttackStep[]
                {
                    new BossAttackStep{ type=BossAttackType.Teleport, duration=0.25f },
                    new BossAttackStep{ type=BossAttackType.Fog, duration=0.2f },
                    new BossAttackStep{ type=BossAttackType.AimedBurst, intParam=7, floatParam=22f, floatParam2=540f, duration=0.45f },
                    new BossAttackStep{ type=BossAttackType.Spiral, intParam=8, floatParam=14f, duration=0.6f },
                    new BossAttackStep{ type=BossAttackType.Clone, duration=0.2f },
                    new BossAttackStep{ type=BossAttackType.Pause, duration=0.45f }
                };
                mistPhase2Pattern = new BossAttackStep[]
                {
                    new BossAttackStep{ type=BossAttackType.Teleport, duration=0.2f },
                    new BossAttackStep{ type=BossAttackType.Volley, intParam=12, floatParam=240f, duration=0.6f },
                    new BossAttackStep{ type=BossAttackType.Spiral, intParam=10, floatParam=12f, duration=0.6f },
                    new BossAttackStep{ type=BossAttackType.Fog, duration=0.2f },
                    new BossAttackStep{ type=BossAttackType.Clone, duration=0.2f },
                    new BossAttackStep{ type=BossAttackType.AimedBurst, intParam=8, floatParam=20f, floatParam2=560f, duration=0.5f },
                    new BossAttackStep{ type=BossAttackType.Pause, duration=0.4f }
                };
            }
            if (behavior == EnemyBehaviorType.BossMemoryDevourer && (devourerPattern == null || devourerPattern.Length == 0))
            {
                devourerPhase0Pattern = new BossAttackStep[]
                {
                    new BossAttackStep{ type=BossAttackType.Hazard, duration=0.2f },
                    new BossAttackStep{ type=BossAttackType.Spiral, intParam=8, floatParam=14f, duration=0.55f },
                    new BossAttackStep{ type=BossAttackType.Summon, duration=0.45f },
                    new BossAttackStep{ type=BossAttackType.Pause, duration=0.45f }
                };
                devourerPhase1Pattern = new BossAttackStep[]
                {
                    new BossAttackStep{ type=BossAttackType.RingHazard, intParam=10, floatParam=3.5f, duration=0.25f },
                    new BossAttackStep{ type=BossAttackType.Spiral, intParam=10, floatParam=12f, duration=0.6f },
                    new BossAttackStep{ type=BossAttackType.Summon, duration=0.4f },
                    new BossAttackStep{ type=BossAttackType.Volley, intParam=12, floatParam=260f, duration=0.6f },
                    new BossAttackStep{ type=BossAttackType.Pause, duration=0.45f }
                };
                devourerPhase2Pattern = new BossAttackStep[]
                {
                    new BossAttackStep{ type=BossAttackType.RingHazard, intParam=12, floatParam=4f, duration=0.25f },
                    new BossAttackStep{ type=BossAttackType.Spiral, intParam=12, floatParam=10f, duration=0.65f },
                    new BossAttackStep{ type=BossAttackType.Summon, duration=0.35f },
                    new BossAttackStep{ type=BossAttackType.AimedBurst, intParam=8, floatParam=18f, floatParam2=560f, duration=0.45f },
                    new BossAttackStep{ type=BossAttackType.Volley, intParam=14, floatParam=280f, duration=0.6f },
                    new BossAttackStep{ type=BossAttackType.Pause, duration=0.4f }
                };
            }
            if ((behavior == EnemyBehaviorType.BossTwinMain || behavior == EnemyBehaviorType.BossTwinPartner) && (twinPattern == null || twinPattern.Length == 0))
            {
                twinPhase0Pattern = new BossAttackStep[]
                {
                    new BossAttackStep{ type=BossAttackType.Volley, intParam=6, floatParam=140f, duration=0.45f },
                    new BossAttackStep{ type=BossAttackType.AimedBurst, intParam=4, floatParam=16f, floatParam2=520f, duration=0.35f },
                    new BossAttackStep{ type=BossAttackType.Spiral, intParam=4, floatParam=30f, duration=0.45f },
                    new BossAttackStep{ type=BossAttackType.Pause, duration=0.4f }
                };
                twinEnragePattern = new BossAttackStep[]
                {
                    new BossAttackStep{ type=BossAttackType.Volley, intParam=8, floatParam=180f, duration=0.45f },
                    new BossAttackStep{ type=BossAttackType.AimedBurst, intParam=6, floatParam=18f, floatParam2=560f, duration=0.35f },
                    new BossAttackStep{ type=BossAttackType.Spiral, intParam=6, floatParam=24f, duration=0.45f },
                    new BossAttackStep{ type=BossAttackType.Pause, duration=0.35f }
                };
            }
        }

        private IEnumerator ExecuteStep(BossAttackStep step)
        {
            switch (step.type)
            {
                case BossAttackType.Pause:
                    yield return new WaitForSeconds(step.duration);
                    break;
                case BossAttackType.Teleport:
                    TeleportNearTarget();
                    yield return new WaitForSeconds(step.duration);
                    break;
                case BossAttackType.Volley:
                    RadialVolley(step.intParam > 0 ? step.intParam : mistVolleyProjectiles, step.floatParam > 0 ? step.floatParam : 180f);
                    yield return new WaitForSeconds(step.duration);
                    break;
                case BossAttackType.Spiral:
                    SpiralVolley(step.intParam > 0 ? step.intParam : devourerSpiralProjectiles, step.floatParam > 0 ? step.floatParam : devourerSpiralStepDeg, ref _devourerSpiralAngle);
                    yield return new WaitForSeconds(step.duration);
                    break;
                case BossAttackType.Fog:
                    SpawnMistFog();
                    yield return new WaitForSeconds(step.duration);
                    break;
                case BossAttackType.Hazard:
                    DropHazard();
                    yield return new WaitForSeconds(step.duration);
                    break;
                case BossAttackType.Summon:
                    factory?.SpawnAround(devourerSummonType, transform.position);
                    yield return new WaitForSeconds(step.duration);
                    break;
                case BossAttackType.Clone:
                    SpawnMistClone();
                    yield return new WaitForSeconds(step.duration);
                    break;
                case BossAttackType.AimedBurst:
                    AimedBurst(step.intParam > 0 ? step.intParam : aimedBurstProjectiles, step.floatParam > 0 ? step.floatParam : aimedBurstSpreadDeg, step.floatParam2 > 0 ? step.floatParam2 : aimedBurstSpeed);
                    yield return new WaitForSeconds(step.duration);
                    break;
                case BossAttackType.RingHazard:
                    RingHazard(step.intParam > 0 ? step.intParam : ringHazardCount, step.floatParam > 0 ? step.floatParam : ringHazardRadius);
                    yield return new WaitForSeconds(step.duration);
                    break;
            }
        }
    }
}
