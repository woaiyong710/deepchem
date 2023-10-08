import deepchem as dc
import numpy as np
import pytest
import tempfile
from flaky import flaky

try:
    import torch
    import torch.nn as nn
    import torch.nn.functional as F

    # helper classes that depend on torch, they need to be in the try/catch block
    class Generator(nn.Module):
        """A simple generator for testing."""

        def __init__(self, noise_input_shape, conditional_input_shape):
            super(Generator, self).__init__()
            self.noise_input_shape = noise_input_shape
            self.conditional_input_shape = conditional_input_shape

            self.noise_dim = noise_input_shape[1:]
            self.conditional_dim = conditional_input_shape[1:]

            input_dim = sum(self.noise_dim) + sum(self.conditional_dim)
            self.output = nn.Linear(input_dim, 1)

        def forward(self, input):
            noise_input, conditional_input = input

            inputs = torch.cat((noise_input, conditional_input), dim=1)
            output = self.output(inputs)
            return output

    class Discriminator(nn.Module):
        """A simple discriminator for testing."""

        def __init__(self, data_input_shape, conditional_input_shape):
            super(Discriminator, self).__init__()
            self.data_input_shape = data_input_shape
            self.conditional_input_shape = conditional_input_shape

            data_dim = data_input_shape[
                1:]  # Extracting the actual data dimension
            conditional_dim = conditional_input_shape[
                1:]  # Extracting the actual conditional dimension
            input_dim = sum(data_dim) + sum(conditional_dim)

            # Define the dense layers
            self.dense1 = nn.Linear(input_dim, 10)
            self.dense2 = nn.Linear(10, 1)

        def forward(self, input):
            data_input, conditional_input = input

            # Concatenate data_input and conditional_input along the second dimension
            discrim_in = torch.cat((data_input, conditional_input), dim=1)

            # Pass the concatenated input through the dense layers
            x = F.relu(self.dense1(discrim_in))
            output = torch.sigmoid(self.dense2(x))

            return output

    class ExampleGAN(dc.models.torch_models.GAN):
        """A simple GAN for testing."""

        def get_noise_input_shape(self):
            return (
                16,
                2,
            )

        def get_data_input_shapes(self):
            return [(
                16,
                1,
            )]

        def get_conditional_input_shapes(self):
            return [(
                16,
                1,
            )]

        def create_generator(self):
            noise_dim = self.get_noise_input_shape()
            conditional_dim = self.get_conditional_input_shapes()[0]

            return nn.Sequential(Generator(noise_dim, conditional_dim))

        def create_discriminator(self):
            data_input_shape = self.get_data_input_shapes()[0]
            conditional_input_shape = self.get_conditional_input_shapes()[0]

            return nn.Sequential(
                Discriminator(data_input_shape, conditional_input_shape))

    class ExampleGANModel(dc.models.torch_models.GANModel):
        """A simple GAN for testing."""

        def get_noise_input_shape(self):
            return (
                100,
                2,
            )

        def get_data_input_shapes(self):
            return [(
                100,
                1,
            )]

        def get_conditional_input_shapes(self):
            return [(
                100,
                1,
            )]

        def create_generator(self):
            noise_dim = self.get_noise_input_shape()
            conditional_dim = self.get_conditional_input_shapes()[0]

            return nn.Sequential(Generator(noise_dim, conditional_dim))

        def create_discriminator(self):
            data_input_shape = self.get_data_input_shapes()[0]
            conditional_input_shape = self.get_conditional_input_shapes()[0]

            return nn.Sequential(
                Discriminator(data_input_shape, conditional_input_shape))

    has_torch = True
except ModuleNotFoundError:
    has_torch = False


@pytest.mark.torch
def create_generator(noise_dim, conditional_dim):
    noise_dim = noise_dim
    conditional_dim = conditional_dim[0]

    return nn.Sequential(Generator(noise_dim, conditional_dim))


@pytest.mark.torch
def create_discriminator(data_input_shape, conditional_input_shape):
    data_input_shape = data_input_shape[0]
    conditional_input_shape = conditional_input_shape[0]

    return nn.Sequential(
        Discriminator(data_input_shape, conditional_input_shape))


@pytest.mark.torch
def test_forward_pass():
    batch_size = 16
    noise_shape = (
        batch_size,
        2,
    )
    data_shape = [(
        batch_size,
        1,
    )]
    conditional_shape = [(
        batch_size,
        1,
    )]

    gan = ExampleGAN(noise_shape, data_shape, conditional_shape,
                     create_generator(noise_shape, conditional_shape),
                     create_discriminator(data_shape, conditional_shape))

    noise = torch.rand(*gan.noise_input_shape)
    real_data = torch.rand(*gan.data_input_shape[0])
    conditional = torch.rand(*gan.conditional_input_shape[0])
    gen_loss, disc_loss = gan([noise, real_data, conditional])

    assert isinstance(gen_loss, torch.Tensor)
    assert gen_loss > 0

    assert isinstance(disc_loss, torch.Tensor)
    assert disc_loss > 0


@pytest.mark.torch
def test_get_noise_batch():
    batch_size = 16
    noise_shape = (
        batch_size,
        2,
    )
    data_shape = [(
        batch_size,
        1,
    )]
    conditional_shape = [(
        batch_size,
        1,
    )]

    gan = ExampleGAN(noise_shape, data_shape, conditional_shape,
                     create_generator(noise_shape, conditional_shape),
                     create_discriminator(data_shape, conditional_shape))
    noise = gan.get_noise_batch(batch_size)
    assert noise.shape == (gan.noise_input_shape)


@pytest.mark.torch
def generate_batch(batch_size):
    """Draw training data from a Gaussian distribution, where the mean  is a conditional input."""
    means = 10 * np.random.random([batch_size, 1])
    values = np.random.normal(means, scale=2.0)
    return means, values


@pytest.mark.torch
def generate_data(gan, batches, batch_size):
    for _ in range(batches):
        means, values = generate_batch(batch_size)
        batch = {gan.data_inputs[0]: values, gan.conditional_inputs[0]: means}
        yield batch


@pytest.mark.torch
def test_cgan():
    """Test fitting a conditional GAN."""

    gan = ExampleGANModel(learning_rate=0.01)
    data = generate_data(gan, 500, 100)
    gan.fit_gan(data, generator_steps=0.5, checkpoint_interval=0)

    # See if it has done a plausible job of learning the distribution.

    means = 10 * np.random.random([1000, 1])
    values = gan.predict_gan_generator(conditional_inputs=[means])
    deltas = values - means
    print("Deltas", abs(np.mean(deltas)))
    assert abs(np.mean(deltas)) < 1.0
    assert np.std(deltas) > 1.0
    assert gan.get_global_step() == 500


@pytest.mark.torch
def test_cgan_reload():
    """Test reloading a conditional GAN."""

    model_dir = tempfile.mkdtemp()
    gan = ExampleGANModel(learning_rate=0.01, model_dir=model_dir)
    gan.fit_gan(generate_data(gan, 500, 100), generator_steps=0.5)

    # See if it has done a plausible job of learning the distribution.
    means = 10 * np.random.random([1000, 1])
    batch_size = len(means)
    noise_input = gan.get_noise_batch(batch_size=batch_size)
    values = gan.predict_gan_generator(noise_input=noise_input,
                                       conditional_inputs=[means])
    deltas = values - means
    assert np.std(deltas) > 1.0
    assert gan.get_global_step() == 500

    reloaded_gan = ExampleGANModel(learning_rate=0.01, model_dir=model_dir)
    reloaded_gan.restore(strict=False)
    reloaded_values = reloaded_gan.predict_gan_generator(
        noise_input=noise_input, conditional_inputs=[means])

    assert np.all(values == reloaded_values)


@flaky
@pytest.mark.torch
def test_mix_gan():
    """Test a GAN with multiple generators and discriminators."""

    gan = ExampleGANModel(n_generators=2,
                          n_discriminators=2,
                          learning_rate=0.01)
    data = generate_data(gan, 1000, 100)
    gan.fit_gan(data, generator_steps=0.5, checkpoint_interval=0)

    # See if it has done a plausible job of learning the distribution.

    means = 10 * np.random.random([1000, 1])
    for i in range(2):
        values = gan.predict_gan_generator(conditional_inputs=[means],
                                           generator_index=i)
        deltas = values - means
        assert abs(np.mean(deltas)) < 1.0
        assert np.std(deltas) > 1.0
    assert gan.get_global_step() == 1000


@flaky
@pytest.mark.torch
def test_mix_gan_reload():
    """Test reloading a GAN with multiple generators and discriminators."""

    model_dir = tempfile.mkdtemp()
    gan = ExampleGANModel(n_generators=2,
                          n_discriminators=2,
                          learning_rate=0.01,
                          model_dir=model_dir)
    gan.fit_gan(generate_data(gan, 1000, 100), generator_steps=0.5)

    reloaded_gan = ExampleGANModel(n_generators=2,
                                   n_discriminators=2,
                                   learning_rate=0.01,
                                   model_dir=model_dir)
    reloaded_gan.restore(strict=False)
    # See if it has done a plausible job of learning the distribution.

    means = 10 * np.random.random([1000, 1])
    batch_size = len(means)
    noise_input = gan.get_noise_batch(batch_size=batch_size)
    for i in range(2):
        values = gan.predict_gan_generator(noise_input=noise_input,
                                           conditional_inputs=[means],
                                           generator_index=i)
        reloaded_values = reloaded_gan.predict_gan_generator(
            noise_input=noise_input,
            conditional_inputs=[means],
            generator_index=i)
        assert np.all(values == reloaded_values)
    assert gan.get_global_step() == 1000
    # No training has been done after reload
    assert reloaded_gan.get_global_step() == 1000
