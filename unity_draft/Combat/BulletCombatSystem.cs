using UnityEngine;
using System.Collections.Generic;
using ZGame.UnityDraft.Systems;
using ZGame.UnityDraft;

namespace ZGame.UnityDraft.Combat
{
    /// <summary>
    /// Handles bullet movement, collisions, and damage application.
    /// Draft mapper from the Python logic: distance cap, crit/shield routing, pierce/ricochet, and hooks for explosive/shrapnel.
    /// </summary>
    public class BulletCombatSystem : MonoBehaviour
    {
        [Tooltip("Layer mask for enemies.")]
        public LayerMask enemyMask;
        [Tooltip("Layer mask for player (for enemy shots).")]
        public LayerMask playerMask;
        [Tooltip("Layer mask for neutral (if used).")]
        public LayerMask neutralMask;
        [Tooltip("Radius for circle hit test (world units).")]
        public float defaultHitRadius = 8f;
        [Tooltip("Reference to shared balance.")]
        public GameBalanceConfig balance;
        [Tooltip("Shrapnel count and damage fraction.")]
        public int shrapnelCount = 4;
        public float shrapnelDamageFrac = 0.4f;
        public float shrapnelRangeFrac = 0.5f;
        public float explosiveRadius = 80f;
        [Header("Crit/Shield")]
        public float critChance = 0.05f;
        public float critMult = 1.8f;
        public int playerShieldHp = 0; // placeholder; tie to player data if needed
        [Header("Friendly Fire")]
        public bool allowEnemyExplosive = false;
        public bool allowEnemyShrapnel = false;
        public bool allowEnemyVsEnemy = false;
        public bool allowPlayerVsPlayer = false; // for co-op future
        [Header("Meta Hooks")]
        public MetaProgression meta;
        public HUDController hud;
        public bool awardKills = true;
        public bool awardSpoils = true;
        [Header("Paint on Hit")]
        public PaintSystem paintSystem;
        public Color paintHitColor = new Color(0.2f, 0.8f, 1f, 0.25f);
        public float paintHitRadius = 0.4f;
        public float paintHitLifetime = 4f;

        private readonly List<Bullet> _bullets = new();
        private readonly Collider2D[] _hitBuffer = new Collider2D[16];
        private BulletPool _bulletPool;

        private void Awake()
        {
            // Optional: auto-find a BulletPool in scene if not set elsewhere
            _bulletPool = GetComponent<BulletPool>();
            // Auto-assign masks to default layers if not set
            if (enemyMask == 0) enemyMask = LayerMask.GetMask("Enemy");
            if (playerMask == 0) playerMask = LayerMask.GetMask("Player");
            // Pull crit from balance if provided
            if (balance != null)
            {
                critChance = balance.critChance;
                critMult = balance.critMult;
                shrapnelCount = balance.shrapnelCount;
                shrapnelDamageFrac = balance.shrapnelDamageFrac;
                shrapnelRangeFrac = balance.shrapnelRangeFrac;
                explosiveRadius = balance.explosiveRadius;
                defaultHitRadius = balance.bulletHitRadius;
            }
        }

        public void RegisterBullet(Bullet b)
        {
            if (b != null) _bullets.Add(b);
        }

        public void Tick(float dt)
        {
            for (int i = _bullets.Count - 1; i >= 0; i--)
            {
                var b = _bullets[i];
                if (!b || !b.gameObject.activeSelf) { _bullets.RemoveAt(i); continue; }
                b.Tick(dt);
                if (!b.alive) { _bullets.RemoveAt(i); continue; }
                ProcessHit(b);
            }
        }

        private void ProcessHit(Bullet b)
        {
            LayerMask mask = enemyMask;
            switch (b.faction)
            {
                case Bullet.Faction.Player:
                    mask = allowPlayerVsPlayer ? (enemyMask | playerMask) : enemyMask;
                    break;
                case Bullet.Faction.Enemy:
                    mask = allowEnemyVsEnemy ? (playerMask | enemyMask) : playerMask;
                    break;
                case Bullet.Faction.Neutral:
                    mask = neutralMask != 0 ? neutralMask : (enemyMask | playerMask);
                    break;
            }
            float radius = b.hitRadius > 0f ? b.hitRadius : defaultHitRadius;
            int count = Physics2D.OverlapCircleNonAlloc(b.transform.position, radius, _hitBuffer, mask);
            if (count <= 0) return;
            for (int i = 0; i < count; i++)
            {
                var col = _hitBuffer[i];
                if (!col) continue;
                if (b.faction == Bullet.Faction.Enemy)
                {
                    var player = col.GetComponentInParent<Player>();
                    if (player == null) continue;
                    ApplyDamageToPlayer(player, b);
                }
                else
                {
                    var enemy = col.GetComponentInParent<Enemy>();
                    if (enemy == null) continue;
                    ApplyDamageToEnemy(enemy, b);
                }
                break; // stop after processing a valid hit
            }
        }

        private void ApplyDamageToEnemy(Enemy enemy, Bullet b)
        {
            ICritSource attacker = b.attacker;
            int dealt = ComputeCritDamage(b.damage, out bool isCrit, attacker);
            // Shield routing for enemies (e.g., shielder buff)
            if (enemy.shieldHp > 0)
            {
                int blocked = Mathf.Min(dealt, enemy.shieldHp);
                enemy.shieldHp -= blocked;
                dealt -= blocked;
            }
            var status = enemy.GetComponent<ZGame.UnityDraft.Systems.StatusEffect>();
            status?.TryAbsorb(ref dealt);
            enemy.hp = Mathf.Max(0, enemy.hp - dealt);
            bool killed = enemy.hp <= 0;
            if (killed)
            {
                enemy.Kill();
                if (meta != null)
                {
                    if (awardKills) meta.AddKill(1);
                    if (awardSpoils && enemy.spoils > 0)
                    {
                        meta.AddRunCoins(enemy.spoils);
                        if (hud != null) hud.SetCoins(meta.runCoins + meta.bankedCoins);
                        enemy.spoils = 0;
                    }
                }
                // Hook: Explosive rounds/shrapnel
                if (b.source == "player" || (b.source == "enemy" && allowEnemyExplosive))
                {
                    TriggerExplosive(enemy.transform.position, b);
                }
                if (b.source == "player" || (b.source == "enemy" && allowEnemyShrapnel))
                {
                    SpawnShrapnel(enemy.transform.position, b);
                }
            }

            // Pierce/ricochet handling
            if (b.pierceLeft > 0)
            {
                b.pierceLeft--;
                return; // keep bullet alive
            }

            if (b.ricochetLeft > 0)
            {
                if (TryRicochet(b, enemy.transform.position))
                {
                    b.ricochetLeft--;
                    return;
                }
            }

            b.alive = false;
            b.gameObject.SetActive(false);

            if (paintSystem != null)
            {
                paintSystem.SpawnEnemyPaint(enemy.transform.position, paintHitRadius, paintHitLifetime, paintHitColor);
            }
        }

        private bool TryRicochet(Bullet b, Vector3 hitPos)
        {
            // Simple: find nearest enemy within a cone; here just pick any within radius.
            float radius = (b.hitRadius > 0f ? b.hitRadius : defaultHitRadius) * 8f;
            int count = Physics2D.OverlapCircleNonAlloc(hitPos, radius, _hitBuffer, enemyMask);
            float bestD2 = float.MaxValue;
            Vector3 bestPos = Vector3.zero;
            for (int i = 0; i < count; i++)
            {
                var col = _hitBuffer[i];
                if (!col) continue;
                var e = col.GetComponentInParent<Enemy>();
                if (e == null || !e.gameObject.activeSelf || e.hp <= 0) continue;
                float d2 = (e.transform.position - hitPos).sqrMagnitude;
                if (d2 < bestD2 && d2 > 0.01f)
                {
                    bestD2 = d2;
                    bestPos = e.transform.position;
                }
            }
            if (bestD2 == float.MaxValue) return false;
            Vector2 dir = (bestPos - hitPos).normalized;
            b.dir = dir;
            b.transform.position = hitPos;
            return true;
        }

        private void ApplyDamageToPlayer(Player player, Bullet b)
        {
            int dealt = Mathf.Max(1, Mathf.RoundToInt(b.damage));
            // Shield routing: subtract from shield if present.
            if (player.shieldHp > 0)
            {
                int blocked = Mathf.Min(dealt, player.shieldHp);
                player.shieldHp -= blocked;
                dealt -= blocked;
            }
            if (dealt > 0)
            {
                player.Damage(dealt);
            }
            if (hitSfx != null)
            {
                AudioSource.PlayClipAtPoint(hitSfx, player.transform.position);
            }
            b.alive = false;
            b.gameObject.SetActive(false);
        }

        // Placeholder hooks for explosive/shrapnel; implement pooling/spawn when VFX/system exists.
        public ExplosionVFX explosionPrefab; // optional VFX
        public ZGame.UnityDraft.VFX.VFXPool vfxPool;
        public AudioClip explosionSfx;
        public AudioClip hitSfx;

        private void TriggerExplosive(Vector3 pos, Bullet b)
        {
            // Apply AoE damage to nearby enemies using defaultHitRadius as baseline for enemies
            float r = explosiveRadius > 0 ? explosiveRadius : defaultHitRadius * 3f;
            int count = Physics2D.OverlapCircleNonAlloc(pos, r, _hitBuffer, enemyMask);
            for (int i = 0; i < count; i++)
            {
                var col = _hitBuffer[i];
                if (!col) continue;
                var enemy = col.GetComponentInParent<Enemy>();
                if (enemy == null || enemy.hp <= 0) continue;
                float aoeFrac = balance != null ? balance.explosiveDamageFrac : 0.75f;
                int dealt = Mathf.Max(1, Mathf.RoundToInt(b.damage * aoeFrac)); // AoE reduced damage
                var status = enemy.GetComponent<ZGame.UnityDraft.Systems.StatusEffect>();
                status?.TryAbsorb(ref dealt);
                enemy.hp = Mathf.Max(0, enemy.hp - dealt);
                if (enemy.hp <= 0)
                {
                    enemy.Kill();
                    if (meta != null)
                    {
                        if (awardKills) meta.AddKill(1);
                        if (awardSpoils && enemy.spoils > 0)
                        {
                            meta.AddRunCoins(enemy.spoils);
                            if (hud != null) hud.SetCoins(meta.runCoins + meta.bankedCoins);
                            enemy.spoils = 0;
                        }
                    }
                }
            }
            if (explosionPrefab != null)
            {
                if (vfxPool != null)
                {
                    var vfx = vfxPool.Get();
                    vfx.transform.position = pos;
                }
                else
                {
                    var vfx = Object.Instantiate(explosionPrefab, pos, Quaternion.identity);
                    vfx.gameObject.SetActive(true);
                }
            }
            if (explosionSfx != null)
            {
                AudioSource.PlayClipAtPoint(explosionSfx, pos);
            }
        }

        private void SpawnShrapnel(Vector3 pos, Bullet b)
        {
            if (_bulletPool == null || shrapnelCount <= 0) return;
            for (int i = 0; i < shrapnelCount; i++)
            {
                float ang = Random.Range(0f, Mathf.PI * 2f);
                Vector2 dir = new Vector2(Mathf.Cos(ang), Mathf.Sin(ang));
                var sb = _bulletPool.Get();
                sb.source = b.source;
                float dmg = b.damage * shrapnelDamageFrac;
                float range = b.maxDist * shrapnelRangeFrac;
                sb.Init(pos, dir, dmg, range, b.speed * 0.85f);
                sb.pierceLeft = 0;
                sb.ricochetLeft = 0;
                sb.hitRadius = b.hitRadius;
                RegisterBullet(sb);
            }
        }

        private int ComputeCritDamage(float baseDamage, out bool isCrit, ICritSource attacker = null)
        {
            float chance = attacker != null ? attacker.CritChance : critChance;
            float mult = attacker != null ? attacker.CritMult : critMult;
            isCrit = Random.value < chance;
            float dmg = baseDamage * (isCrit ? mult : 1f);
            return Mathf.Max(1, Mathf.RoundToInt(dmg));
        }
    }
}
