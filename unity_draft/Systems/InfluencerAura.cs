using UnityEngine;

namespace ZGame.UnityDraft.Systems
{
    /// <summary>
    /// Influencer enemy aura: slows and reduces player damage when nearby.
    /// </summary>
    public class InfluencerAura : MonoBehaviour
    {
        public float radius = 3f;
        public float speedMult = 0.85f;
        public float attackMult = 0.9f;
        public float cooldown = 0.25f;
        [Tooltip("Strength decays per second when outside radius.")]
        public float decayRate = 1.5f;
        private float _cd;
        private readonly System.Collections.Generic.Dictionary<Player, float> _strength = new();

        private void Update()
        {
            _cd -= Time.deltaTime;
            if (_cd > 0f) return;
            _cd = cooldown;
            // accumulate strength by distance
            var hits = Physics2D.OverlapCircleAll(transform.position, radius, LayerMask.GetMask("Player"));
            var seen = new System.Collections.Generic.HashSet<Player>();
            foreach (var h in hits)
            {
                var p = h.GetComponentInParent<Player>();
                if (p == null) continue;
                seen.Add(p);
                float dist = Vector2.Distance(transform.position, p.transform.position);
                float t = Mathf.Clamp01(1f - dist / Mathf.Max(0.001f, radius)); // closer => stronger
                if (_strength.ContainsKey(p))
                    _strength[p] = Mathf.Max(_strength[p], t);
                else
                    _strength[p] = t;
            }
            // decay and apply
            var keys = new System.Collections.Generic.List<Player>(_strength.Keys);
            foreach (var p in keys)
            {
                float s = _strength[p];
                if (!seen.Contains(p))
                {
                    s = Mathf.Max(0f, s - decayRate * Time.deltaTime);
                }
                if (s <= 0f)
                {
                    _strength.Remove(p);
                    continue;
                }
                _strength[p] = s;
                float spMult = Mathf.Lerp(1f, speedMult, s);
                float atkMult = Mathf.Lerp(1f, attackMult, s);
                p.speed *= spMult;
                p.attack = Mathf.Max(1, Mathf.RoundToInt(p.attack * atkMult));
            }
        }
    }
}
