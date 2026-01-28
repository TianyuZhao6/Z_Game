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
        public float cooldown = 0.5f;
        private float _cd;

        private void Update()
        {
            _cd -= Time.deltaTime;
            if (_cd > 0f) return;
            _cd = cooldown;
            var hits = Physics2D.OverlapCircleAll(transform.position, radius, LayerMask.GetMask("Player"));
            foreach (var h in hits)
            {
                var p = h.GetComponentInParent<Player>();
                if (p != null)
                {
                    p.speed *= speedMult;
                    p.attack = Mathf.Max(1, Mathf.RoundToInt(p.attack * attackMult));
                }
            }
        }
    }
}
