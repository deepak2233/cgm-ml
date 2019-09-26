'''
This script trains PointNet.
'''
import sys
sys.path.insert(0, "..")
import warnings
warnings.filterwarnings("ignore")
from cgmcore import modelutils
from cgmcore import utils
import numpy as np
from tensorflow.keras import callbacks, optimizers, models, layers
import pprint
import os
from cgmcore.preprocesseddatagenerator import get_dataset_path, create_datagenerator_from_parameters
import random
import qrcodes
from cgmcore.utils import create_training_tasks
import multiprocessing

# Get the dataset path.
if len(sys.argv) == 1:
    dataset_path = get_dataset_path()
else:
    dataset_path = sys.argv[1]
print("Using dataset path", dataset_path)

output_root_path = "/whhdata/models"

# Hyperparameters.
steps_per_epoch = 1000
validation_steps = 200
epochs = 100
batch_size = 16
random_seed = 667

if len(utils.get_available_gpus()) == 0:
    output_root_path = "."
    steps_per_epoch = 1
    validation_steps = 1
    epochs = 2
    batch_size = 1
    random_seed = 667
    print("WARNING! No GPU available!")

    
image_size = 128

# For creating pointclouds.
dataset_parameters = {}
dataset_parameters["input_type"] = "pointcloud"
dataset_parameters["output_targets"] = ["height"]
dataset_parameters["random_seed"] = random_seed
dataset_parameters["pointcloud_target_size"] = 10000
dataset_parameters["pointcloud_random_rotation"] = False
dataset_parameters["pointcloud_subsampling_method"] = "sequential_skip"
dataset_parameters["sequence_length"] = 0
datagenerator_instance = create_datagenerator_from_parameters(dataset_path, dataset_parameters)

# Get the QR-codes.
qrcodes = datagenerator_instance.qrcodes[:]
subset_sizes = [1.0]    
qrcodes_tasks = create_training_tasks(qrcodes, subset_sizes)

# Go through all.
for qrcodes_task in qrcodes_tasks:
    
    qrcodes_train, qrcodes_validate = qrcodes_task
    print("Using {} QR-codes for training.".format(len(qrcodes_train)))
    print("Using {} QR-codes for validation.".format(len(qrcodes_validate)))

    # Create python generators.
    workers = 4
    generator_train = datagenerator_instance.generate(
        size=batch_size, 
        qrcodes_to_use=qrcodes_train, 
        workers=workers
    )
    generator_validate = datagenerator_instance.generate(
        size=batch_size,
        qrcodes_to_use=qrcodes_validate,
        workers=workers)

    # Testing the genrators.
    def test_generator(generator):
        data = next(generator)
        print("Input:", data[0].shape, "Output:", data[1].shape)
    test_generator(generator_train)
    test_generator(generator_validate)

    # Training details.
    training_details = {
        "dataset_path" : dataset_path,
        "qrcodes_train" : qrcodes_train,
        "qrcodes_validate" : qrcodes_validate,
        "steps_per_epoch" : steps_per_epoch,
        "validation_steps" : validation_steps,
        "epochs" : epochs,
        "batch_size" : batch_size,
        "random_seed" : random_seed,
        "dataset_parameters" : dataset_parameters,
        "hidden_sizes" : [512, 256, 128]
    }

    # Date time string.
    datetime_string = utils.get_datetime_string() + "_{}-{}".format(len(qrcodes_train), len(qrcodes_validate)) + "_".join(dataset_parameters["output_targets"])
    if len(sys.argv) > 2:
        datetime_string += "-" + sys.argv[2]

    # Output path. Ensure its existence.
    output_path = os.path.join(output_root_path, datetime_string)
    print("Using output path:", output_path)
    if os.path.exists(output_path) == False:
        os.makedirs(output_path)

    # Important things.
    pp = pprint.PrettyPrinter(indent=4)
    log_dir = os.path.join("/whhdata/models", "logs", datetime_string)
    tensorboard_callback = callbacks.TensorBoard(log_dir=log_dir)
    histories = {}

    # Stopping early based on the loss.
    #early_stopping_callback = callbacks.EarlyStopping(
    #    monitor="val_loss",
    #    restore_best_weights=True,
    #    patience = 10
    #)

    # Training network.
    def train_pointclouds():

        input_shape = (dataset_parameters["pointcloud_target_size"], 3)
        output_size = 1
        model = modelutils.create_point_net(input_shape, output_size, hidden_sizes=training_details["hidden_sizes"] )
        model.summary()

        # Compile the model.
        #optimizer = optimizers.RMSprop(lr=0.0001)
        optimizer = optimizers.RMSprop()
        model.compile(
                optimizer=optimizer,
                loss="mse",
                metrics=["mae"]
            )

        try:
            # Train the model.
            history = model.fit_generator(
                generator_train,
                steps_per_epoch=steps_per_epoch,
                epochs=epochs,
                validation_data=generator_validate,
                validation_steps=validation_steps,
                use_multiprocessing=False,
                workers=0,
                callbacks=[tensorboard_callback]
                )
        except KeyboardInterrupt:
            print("Gracefully finishing on user request...")
            datagenerator_instance.finish()
            

        histories["pointnet"] = history
        modelutils.save_model_and_history(output_path, datetime_string, model, history, training_details, "pointnet")

    train_pointclouds()