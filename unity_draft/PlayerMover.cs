using UnityEngine;
using ZGame.UnityDraft.Systems;

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
        [Header("Dash")]
        public KeyCode dashKey = KeyCode.Space;
        public float dashSpeedMult = 2.5f;
        public float dashDuration = 0.25f;
        public float dashCooldown = 1.0f;

        private Player _player;
        private Rigidbody2D _rb;
        private ObstacleCrushOnContact _crush;
        private Vector2 _lastDir = Vector2.right;
        private float _dashTimer = 0f;
        private float _dashCd = 0f;

        private void Awake()
        {
            _player = GetComponent<Player>();
            _rb = GetComponent<Rigidbody2D>();
            _crush = GetComponent<ObstacleCrushOnContact>();
        }

        private void Update()
        {
            if (_dashCd > 0f) _dashCd -= Time.deltaTime;
            if (_dashTimer > 0f)
            {
                _dashTimer -= Time.deltaTime;
                if (_dashTimer <= 0f)
                {
                    EndDash();
                }
            }

            if (Input.GetKeyDown(dashKey) && _dashCd <= 0f)
            {
                StartDash();
            }
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
                _lastDir = input;
            }
            else
            {
                vel = Vector2.MoveTowards(vel, Vector2.zero, decel * Time.fixedDeltaTime);
            }

            if (_dashTimer > 0f)
            {
                Vector2 dir = _lastDir.sqrMagnitude > 0.01f ? _lastDir : (vel.sqrMagnitude > 0.01f ? vel.normalized : Vector2.right);
                vel = dir * targetSpeed * dashSpeedMult;
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

        private void StartDash()
        {
            _dashTimer = dashDuration;
            _dashCd = dashCooldown;
            if (_crush != null) _crush.isCrushing = true;
        }

        private void EndDash()
        {
            _dashTimer = 0f;
            if (_crush != null) _crush.isCrushing = false;
        }
    }
}
