using UnityEngine;

namespace ZGame.UnityDraft
{
    /// <summary>
    /// Simple WASD player movement for testing. Replace with Input System if desired.
    /// </summary>
    [RequireComponent(typeof(Player))]
    public class PlayerMover : MonoBehaviour
    {
        public float accel = 20f;
        public float decel = 30f;

        private Player _player;
        private Rigidbody2D _rb;

        private void Awake()
        {
            _player = GetComponent<Player>();
            _rb = GetComponent<Rigidbody2D>();
        }

        private void FixedUpdate()
        {
            Vector2 input = new Vector2(Input.GetAxisRaw("Horizontal"), Input.GetAxisRaw("Vertical"));
            Vector2 vel = _rb ? _rb.velocity : Vector2.zero;
            float targetSpeed = _player != null ? _player.speed : 4.5f;

            if (input.sqrMagnitude > 0.01f)
            {
                input.Normalize();
                vel = Vector2.MoveTowards(vel, input * targetSpeed, accel * Time.fixedDeltaTime);
            }
            else
            {
                vel = Vector2.MoveTowards(vel, Vector2.zero, decel * Time.fixedDeltaTime);
            }

            if (_rb)
            {
                _rb.velocity = vel;
            }
            else
            {
                transform.position += (Vector3)(vel * Time.fixedDeltaTime);
            }
        }
    }
}
