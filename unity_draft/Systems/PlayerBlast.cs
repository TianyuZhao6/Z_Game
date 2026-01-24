using UnityEngine;
using ZGame.UnityDraft.Combat;

namespace ZGame.UnityDraft.Systems
{
    /// <summary>
    /// Simple radial blast ability for the player. Damages enemies in range and applies slow/paint if set.
    /// </summary>
    public class PlayerBlast : MonoBehaviour
    {
        public GameBalanceConfig balance;
        public BulletCombatSystem combat;
        public float radius = 2.5f;
        public int damage = 20;
        public float cooldown = 6f;
        public float slowAmount = 0.3f;
        public float slowDuration = 2f;
        public bool applyPaint = false;
        public bool applyAcid = false;
        private float _cd;

        private void Awake()
        {
            if (combat == null) combat = FindObjectOfType<BulletCombatSystem>();
        }

        private void Update()
        {
            _cd = Mathf.Max(0f, _cd - Time.deltaTime);
            if (Input.GetKeyDown(KeyCode.Q) && _cd <= 0f)
            {
                Cast();
            }
        }

        private void Cast()
        {
            _cd = cooldown;
            var hits = Physics2D.OverlapCircleAll(transform.position, radius, combat != null ? combat.enemyMask : LayerMask.GetMask("Enemy"));
            foreach (var h in hits)
            {
                var e = h.GetComponentInParent<Enemy>();
                if (e == null) continue;
                e.Damage(damage);
                if (slowAmount > 0f) StatusEffect.ApplySlow(e.gameObject, slowAmount, slowDuration);
                if (applyPaint) StatusEffect.ApplyPaint(e.gameObject, slowDuration);
                if (applyAcid) StatusEffect.ApplyAcid(e.gameObject, damagePerSecond:5, duration:2f);
            }
        }
    }
}
