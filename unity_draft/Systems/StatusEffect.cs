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

        private readonly List<EffectInstance> _effects = new();
        private Enemy _enemy;
        private Player _player;

        private void Awake()
        {
            _enemy = GetComponent<Enemy>();
            _player = GetComponent<Player>();
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
                        }
                    }
                }
                if (e.duration <= 0f)
                {
                    _effects.RemoveAt(i);
                    if (e.id == "slow") slowMult = 1f;
                    if (e.id == "paint") painted = false;
                    if (e.id == "acid") acid = false;
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
            s.slowMult = Mathf.Clamp01(1f - amount);
            s._effects.Add(new EffectInstance { id = "slow", magnitude = amount, duration = duration });
            if (s._enemy != null) s._enemy.speed *= s.slowMult;
        }

        public static void ApplyPaint(GameObject go, float duration)
        {
            var s = go.GetComponent<StatusEffect>() ?? go.AddComponent<StatusEffect>();
            s.painted = true;
            s._effects.Add(new EffectInstance { id = "paint", duration = duration });
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
