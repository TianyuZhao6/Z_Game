using UnityEngine;

namespace ZGame.UnityDraft.Systems
{
    /// <summary>
    /// Attach to player/enemy to crush DestructibleObstacle when a flag is set (e.g., during dash).
    /// Toggle isCrushing true during dash/charge, false otherwise.
    /// </summary>
    public class ObstacleCrushOnContact : MonoBehaviour
    {
        public bool isCrushing = false;
        public float minImpactSpeed = 6f;

        private Rigidbody2D _rb;

        private void Awake()
        {
            _rb = GetComponent<Rigidbody2D>();
        }

        private void OnCollisionEnter2D(Collision2D collision)
        {
            TryCrush(collision.collider);
        }

        private void OnTriggerEnter2D(Collider2D other)
        {
            TryCrush(other);
        }

        private void TryCrush(Collider2D col)
        {
            if (!isCrushing) return;
            if (_rb != null && _rb.velocity.magnitude < minImpactSpeed) return;
            var d = col.GetComponentInParent<DestructibleObstacle>();
            if (d != null) d.Crush();
        }
    }
}
