using UnityEngine;
using System.Collections.Generic;

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
                critChance = 0.05f; // align with ZGame.py CRIT_CHANCE_BASE
                critMult = 1.8f;    // align with CRIT_MULT_BASE
            }
        }

        public void RegisterBullet(Bullet b) => _bullets.Add(b);

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
            LayerMask mask = b.source == "enemy" ? playerMask : enemyMask;
            float radius = b.hitRadius > 0f ? b.hitRadius : defaultHitRadius;
            int count = Physics2D.OverlapCircleNonAlloc(b.transform.position, radius, _hitBuffer, mask);
            if (count <= 0) return;
            for (int i = 0; i < count; i++)
            {
                var col = _hitBuffer[i];
                if (!col) continue;
                if (b.source == "enemy")
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
            int dealt = ComputeCritDamage(b.damage, out bool isCrit);
            enemy.hp = Mathf.Max(0, enemy.hp - dealt);
            bool killed = enemy.hp <= 0;
            if (killed)
            {
                enemy.gameObject.SetActive(false);
                // Hook: Explosive rounds/shrapnel
                TriggerExplosive(enemy.transform.position, b);
                SpawnShrapnel(enemy.transform.position, b);
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
            b.alive = false;
            b.gameObject.SetActive(false);
        }

        // Placeholder hooks for explosive/shrapnel; implement pooling/spawn when VFX/system exists.
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
                int dealt = Mathf.Max(1, Mathf.RoundToInt(b.damage * 0.75f)); // AoE reduced damage
                enemy.hp = Mathf.Max(0, enemy.hp - dealt);
                if (enemy.hp <= 0)
                {
                    enemy.gameObject.SetActive(false);
                }
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

        private int ComputeCritDamage(float baseDamage, out bool isCrit)
        {
            float chance = critChance;
            float mult = critMult;
            if (balance != null)
            {
                // If balance exposed crit values, plug them here; defaults already match Python.
            }
            isCrit = Random.value < chance;
            float dmg = baseDamage * (isCrit ? mult : 1f);
            return Mathf.Max(1, Mathf.RoundToInt(dmg));
        }
    }
}
