using UnityEngine;
using System.Collections.Generic;

namespace ZGame.UnityDraft.Systems
{
    /// <summary>
    /// Lightweight status effect registry for slows, paint, acid DoT, bone plating, and carapace shields.
    /// Attach to Player or Enemy to tick effects.
    /// </summary>
    public class StatusEffect : MonoBehaviour
    {
        public class EffectInstance
        {
            public string id;
            public float magnitude;
            public float duration;
            public float tickDamage;
            public float tickInterval;
            public float tickTimer;
        }

        public float slowMult = 1f;
        public float bonePlatingHp = 0f;
        public float carapaceHp = 0f;
        public bool painted = false;
        public bool acid = false;
        public bool vulnerable = false;
        public float vulnerabilityMult = 1.0f;
        [Header("Paint Hooks")]
        public PaintSystem paintSystem;
        public Color paintColor = new Color(0.2f, 0.8f, 1f, 0.35f);
        public Color acidColor = new Color(0.4f, 1f, 0.4f, 0.35f);
        public float paintRadius = 0.5f;
        public float paintLifetime = 6f;
        public float acidRadius = 0.4f;
        public float acidLifetime = 4f;

        private readonly List<EffectInstance> _effects = new();
        private Enemy _enemy;
        private Player _player;
        private static PaintSystem _defaultPaint;

        private void Awake()
        {
            _enemy = GetComponent<Enemy>();
            _player = GetComponent<Player>();
            if (paintSystem == null)
            {
                paintSystem = _defaultPaint ?? FindObjectOfType<PaintSystem>();
                _defaultPaint = paintSystem;
            }
        }

        private void Update()
        {
            float dt = Time.deltaTime;
            for (int i = _effects.Count - 1; i >= 0; i--)
            {
                var e = _effects[i];
                e.duration -= dt;
                if (e.tickInterval > 0f)
                {
                    e.tickTimer -= dt;
                    if (e.tickTimer <= 0f)
                    {
                        e.tickTimer = e.tickInterval;
                        if (e.tickDamage > 0f)
                        {
                            ApplyDamageTick(Mathf.RoundToInt(e.tickDamage));
                            if (acid && paintSystem != null)
                            {
                                paintSystem.SpawnEnemyPaint(transform.position, acidRadius, acidLifetime, acidColor);
                            }
                        }
                    }
                }
                if (e.duration <= 0f)
                {
                    _effects.RemoveAt(i);
                    if (e.id == "slow") slowMult = 1f;
                    if (e.id == "paint") painted = false;
                    if (e.id == "acid") acid = false;
                    if (e.id == "vuln") { vulnerable = false; vulnerabilityMult = 1f; }
                }
            }
        }

        private void ApplyDamageTick(int dmg)
        {
            if (_enemy != null) _enemy.Damage(dmg);
            if (_player != null) _player.Damage(dmg);
        }

        public static void ApplySlow(GameObject go, float amount, float duration)
        {
            var s = go.GetComponent<StatusEffect>() ?? go.AddComponent<StatusEffect>();
            float resist = 0f;
            var p = go.GetComponent<Player>();
            if (p != null) resist = p.slowResist;
            float effective = Mathf.Clamp01(amount * (1f - resist));
            s.slowMult = Mathf.Clamp01(1f - effective);
            s._effects.Add(new EffectInstance { id = "slow", magnitude = amount, duration = duration });
            if (s._enemy != null) s._enemy.speed *= s.slowMult;
            if (p != null) p.speed *= s.slowMult;
        }

        public static void ApplyPaint(GameObject go, float duration)
        {
            var s = go.GetComponent<StatusEffect>() ?? go.AddComponent<StatusEffect>();
            s.painted = true;
            s._effects.Add(new EffectInstance { id = "paint", duration = duration });
            if (s.paintSystem != null)
            {
                s.paintSystem.SpawnEnemyPaint(go.transform.position, s.paintRadius, s.paintLifetime, s.paintColor);
            }
            // Wind biome synergy: if target is enemy and balance name matches, extend duration
            var enemy = go.GetComponent<Enemy>();
            if (enemy != null && enemy.balance != null && enemy.balance.name == "Domain of Wind")
            {
                s._effects[^1].duration *= 1.2f;
            }
        }

        public static void ApplyAcid(GameObject go, float damagePerSecond, float duration)
        {
            var s = go.GetComponent<StatusEffect>() ?? go.AddComponent<StatusEffect>();
            s.acid = true;
            s._effects.Add(new EffectInstance
            {
                id = "acid",
                duration = duration,
                tickDamage = damagePerSecond,
                tickInterval = 1f,
                tickTimer = 1f
            });
            if (s.paintSystem != null)
            {
                s.paintSystem.SpawnEnemyPaint(go.transform.position, s.acidRadius, s.acidLifetime, s.acidColor);
            }
        }

        public static void ApplyVulnerability(GameObject go, float mult, float duration)
        {
            var s = go.GetComponent<StatusEffect>() ?? go.AddComponent<StatusEffect>();
            s.vulnerable = true;
            s.vulnerabilityMult = Mathf.Max(1f, mult);
            s._effects.Add(new EffectInstance { id = "vuln", duration = duration });
        }

        public static void ApplyBonePlating(GameObject go, float hp)
        {
            var s = go.GetComponent<StatusEffect>() ?? go.AddComponent<StatusEffect>();
            s.bonePlatingHp = Mathf.Max(s.bonePlatingHp, hp);
        }

        public static void ApplyCarapace(GameObject go, float hp)
        {
            var s = go.GetComponent<StatusEffect>() ?? go.AddComponent<StatusEffect>();
            s.carapaceHp = Mathf.Max(s.carapaceHp, hp);
        }

        public bool TryAbsorb(ref int dmg)
        {
            if (bonePlatingHp > 0f)
            {
                float blocked = Mathf.Min(dmg, bonePlatingHp);
                bonePlatingHp -= blocked;
                dmg -= Mathf.RoundToInt(blocked);
                if (dmg <= 0) return true;
            }
            if (carapaceHp > 0f)
            {
                float blocked = Mathf.Min(dmg, carapaceHp);
                carapaceHp -= blocked;
                dmg -= Mathf.RoundToInt(blocked);
                if (dmg <= 0) return true;
            }
            return false;
        }
    }
}
